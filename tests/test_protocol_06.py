from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.entries import generate_entry_id, validate_evidence
from memory_custodian.locking import (
    LockError,
    MALFORMED_LOCK_RECOVERY_AGE_SECONDS,
    PrivateStateError,
    lock_path,
    mutation_lock,
    read_private_file,
    stale_lock,
)
from tests.cli_test_support import main
from tests.cli_test_support import _subject_for_add
from memory_custodian.main import main as raw_main
from memory_custodian.plans import (
    MutationPlan,
    PENDING_PLAN_MAX_AGE_SECONDS,
    discard_pending_seed,
    pending_entry_suffixes,
    pending_project_id,
)
from memory_custodian.mutations import TextMutation
from memory_custodian.protocol import budget_state, count_inbox_items, estimate_tokens
from memory_custodian.scanning import scan_text
from memory_custodian import compact as compact_module
from memory_custodian import forget as forget_module
from memory_custodian.add import _title


def preview(argv: list[str]) -> tuple[str, str]:
    output = StringIO()
    with redirect_stdout(output):
        assert main(argv) == 0
    match = re.search(r"Plan ID: ([0-9a-f]{16})", output.getvalue())
    assert match, output.getvalue()
    return match.group(1), output.getvalue()


def preview_id(argv: list[str]) -> str:
    return preview(argv)[0]


class Protocol06Tests(unittest.TestCase):
    def test_budget_state_boundaries(self):
        self.assertEqual(budget_state(639, 800), "OK")
        self.assertEqual(budget_state(640, 800), "NEAR LIMIT")
        self.assertEqual(budget_state(800, 800), "NEAR LIMIT")
        self.assertEqual(budget_state(801, 800), "OVER BUDGET")

    def test_generated_title_truncation_does_not_leave_trailing_whitespace(self):
        title = _title(
            "Use one mutation guard and separate private execution plans from public previews."
        )
        self.assertEqual(title, title.rstrip())
        self.assertLessEqual(len(title), 72)

    def test_plan_is_repo_relative_portable_and_has_separate_public_shape(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            roots = (Path(first_tmp), Path(second_tmp))
            plans = []
            for root in roots:
                target = root / "docs" / "memory" / "decisions.md"
                target.parent.mkdir(parents=True)
                target.write_text("before\n", encoding="utf-8")
                plans.append(
                    MutationPlan(
                        "forget",
                        {"topic": "PrivateMarker", "mode": "hard"},
                        "12345678-1234-4234-8234-123456789abc",
                        "0.6",
                        (TextMutation(target, "after\n"),),
                        project_root=root,
                        public_arguments={"topic": "[redacted]", "mode": "hard"},
                        private_context={
                            "privacy_nonce": "89abcdef89abcdef89abcdef89abcdef"
                        },
                        sensitive=True,
                    )
                )

            self.assertEqual(plans[0].plan_id, plans[1].plan_id)
            public = json.dumps(plans[0].canonical(), sort_keys=True)
            private = json.dumps(plans[0].private_canonical(), sort_keys=True)
            self.assertIn("docs/memory/decisions.md", public)
            self.assertNotIn(str(roots[0]), public)
            self.assertNotIn("PrivateMarker", public)
            self.assertNotIn("base_sha256", public)
            self.assertIn("PrivateMarker", private)
            self.assertIn("base_sha256", private)

    def test_plan_canonicalizes_nested_path_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "docs" / "memory" / "decisions.md"
            target.parent.mkdir(parents=True)
            plan = MutationPlan(
                "test",
                {"nested": {"path": target}},
                "12345678-1234-4234-8234-123456789abc",
                "0.6",
                (TextMutation(target, "after\n"),),
                context={"paths": [target]},
                project_root=root,
            )
            canonical = json.dumps(plan.private_canonical(), sort_keys=True)
            self.assertNotIn(str(root), canonical)
            self.assertEqual(
                plan.private_canonical()["arguments"]["nested"]["path"],
                "docs/memory/decisions.md",
            )

    def test_sensitive_plan_redacts_topic_from_public_paths_and_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "docs" / "memory" / "areas" / "PrivateMarker.md"
            target.parent.mkdir(parents=True)
            plan = MutationPlan(
                "forget",
                {"topic": "PrivateMarker", "mode": "hard"},
                "12345678-1234-4234-8234-123456789abc",
                "0.6",
                (TextMutation(target, "after\n"),),
                blockers=("areas/PrivateMarker.md: requires review",),
                project_root=root,
                public_arguments={"topic": "[redacted]", "mode": "hard"},
                private_context={
                    "privacy_nonce": "89abcdef89abcdef89abcdef89abcdef"
                },
                sensitive=True,
                public_redactions=("PrivateMarker",),
            )
            public = json.dumps(plan.canonical(), sort_keys=True)
            private = json.dumps(plan.private_canonical(), sort_keys=True)
            self.assertNotIn("PrivateMarker", public)
            self.assertIn("areas/[redacted].md", public)
            self.assertIn("PrivateMarker", private)

    @unittest.skipIf(os.name == "nt", "POSIX permission and symlink semantics")
    def test_private_plan_state_is_0700_0600_and_rejects_symlink_files(self):
        with tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as project:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                _values, seed = pending_entry_suffixes(
                    "permission-test",
                    Path(project),
                    "source-digest",
                    ["one"],
                )
                assert seed is not None
                plan_dir = Path(state) / "memory-custodian" / "plans"
                self.assertEqual(plan_dir.stat().st_mode & 0o777, 0o700)
                self.assertEqual(seed.stat().st_mode & 0o777, 0o600)
                discard_pending_seed(seed)

                outside = Path(state) / "outside"
                outside.write_text("do not read\n", encoding="utf-8")
                malicious = plan_dir / "permission-test-malicious.json"
                malicious.symlink_to(outside)
                with self.assertRaises(PrivateStateError):
                    read_private_file(malicious)

    def test_check_rejects_duplicate_fields_wrong_body_and_lifecycle_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            constraint = Path(tmp) / "docs" / "memory" / "constraints.md"
            constraint.write_text(
                "# Constraints\n\n"
                "## MC-CON-20260729-a1b2c3d4 — Malformed structured entry\n\n"
                "Status: active\n"
                "Status: superseded\n"
                "Scope: project\n"
                "Evidence:\n"
                "- user-confirmed\n"
                "Evidence:\n"
                "- user-confirmed\n"
                "Superseded-By: MC-CON-20260729-b2c3d4e5\n"
                "Superseded-By: MC-CON-20260729-b2c3d4e5\n"
                "Promoted-To: MC-CON-20260729-c3d4e5f6\n\n"
                "Decision:\n"
                "This body has the wrong type.\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["check", "--project-root", tmp]), 1)
            text = output.getvalue()
            self.assertIn("must declare exactly one Status field", text)
            self.assertIn("has duplicate Evidence fields", text)
            self.assertIn("has duplicate Superseded-By fields", text)
            self.assertIn("must declare exactly one Constraint typed body", text)
            self.assertIn("uses Decision body", text)
            self.assertIn("cannot declare both Superseded-By and Promoted-To", text)

    def test_check_enforces_bidirectional_type_storage_and_area_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nValidate storage.\n\n"
                "Current direction:\n- Keep schemas canonical.\n",
                encoding="utf-8",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n"
                "## MC-DEC-20260729-a1b2c3d4 — Misplaced decision\n\n"
                "Status: active\n"
                "Scope: project\n"
                "Evidence:\n"
                "- user-confirmed\n\n"
                "Decision:\n"
                "This decision is in the wrong canonical file.\n",
                encoding="utf-8",
            )
            area = memory / "areas" / "backend.md"
            area.parent.mkdir(parents=True)
            area.write_text(
                "# Area: Backend\n\n"
                "## MC-AREA-20260729-b2c3d4e5 — Wrong scope\n\n"
                "Status: active\n"
                "Scope: project\n"
                "Evidence:\n"
                "- user-confirmed\n\n"
                "Decision:\n"
                "Area storage requires its matching area scope.\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["check", "--project-root", tmp]), 1)
            text = output.getvalue()
            self.assertIn(
                "MC-DEC-20260729-a1b2c3d4 type does not match its storage location",
                text,
            )
            self.assertIn(
                "MC-AREA-20260729-b2c3d4e5 must use Scope: area:backend",
                text,
            )

    def test_entry_id_format_and_collision_retry(self):
        with patch("memory_custodian.entries.uuid.uuid4") as generated:
            generated.side_effect = [
                uuid.UUID("aaaaaaaa-0000-4000-8000-000000000000"),
                uuid.UUID("bbbbbbbb-0000-4000-8000-000000000000"),
            ]
            value = generate_entry_id(
                "decision",
                {"MC-DEC-20260728-aaaaaaaa"},
                day=date(2026, 7, 28),
            )
        self.assertEqual(value, "MC-DEC-20260728-bbbbbbbb")

    def test_evidence_path_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            self.assertEqual(
                validate_evidence(["repo:pyproject.toml"], root),
                ("repo:pyproject.toml",),
            )
            with self.assertRaises(ValueError):
                validate_evidence(["repo:../secret"], root)
            with self.assertRaises(ValueError):
                validate_evidence(["agent-observed"], root)

    def test_active_add_rejects_missing_and_unconfirmed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            before = (Path(tmp) / "docs" / "memory" / "decisions.md").read_text(encoding="utf-8")
            self.assertEqual(
                raw_main(["add", "Unsupported", "--type", "decision", "--project-root", tmp]),
                2,
            )
            self.assertEqual(
                raw_main([
                    "add", "Unsupported", "--type", "decision",
                    "--evidence", "agent-observed", "--project-root", tmp,
                ]),
                2,
            )
            self.assertEqual(
                (Path(tmp) / "docs" / "memory" / "decisions.md").read_text(encoding="utf-8"),
                before,
            )

    def test_check_rejects_duplicate_id_invalid_status_scope_and_candidate_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            entry_id = "MC-CON-20260728-a1b2c3d4"
            malformed = (
                "# Constraints\n\n"
                f"## {entry_id} — Invalid one\n\n"
                "Status: mystery\nScope: outside\nEvidence:\n- user-confirmed\n\nConstraint:\nOne.\n\n"
                f"## {entry_id} — Invalid two\n\n"
                "Status: candidate\nScope: project\nEvidence:\n- agent-observed\n\nStatement:\nTwo.\n"
            )
            (memory / "constraints.md").write_text(malformed, encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = main(["check", "--project-root", tmp])
            text = output.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("invalid Status", text)
            self.assertIn("invalid Scope", text)
            self.assertIn("must be stored in inbox.md", text)
            self.assertIn("duplicate Entry ID", text)

    def test_check_rejects_active_inbox_and_broken_relations(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            inbox = Path(tmp) / "docs" / "memory" / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n"
                "## MC-INBOX-20260728-a1b2c3d4 — Invalid active inbox entry\n\n"
                "Status: active\n"
                "Scope: project\n"
                "Evidence:\n"
                "- user-confirmed\n\n"
                "Supersedes: MC-CON-20260728-ffffffff\n\n"
                "Statement:\nInvalid.\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                code = main(["check", "--project-root", tmp])
            text = output.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("inbox entries must be candidate or promoted", text)
            self.assertIn("references missing entry", text)

    def test_repair_preserves_project_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            before = re.search(r"project_id: ([0-9a-f-]+)", manifest.read_text(encoding="utf-8")).group(1)
            self.assertEqual(main(["init", "--repair", "--project-root", tmp]), 0)
            after = re.search(r"project_id: ([0-9a-f-]+)", manifest.read_text(encoding="utf-8")).group(1)
            self.assertEqual(before, after)

    def test_active_candidate_and_supersede(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(
                main([
                    "add", "Keep runtime offline.", "--type", "constraint",
                    "--evidence", "user-confirmed", "--project-root", tmp,
                ]),
                0,
            )
            memory = Path(tmp) / "docs" / "memory"
            constraints = (memory / "constraints.md").read_text(encoding="utf-8")
            old_id = re.search(r"MC-CON-\d{8}-[0-9a-f]{8}", constraints).group(0)
            self.assertIn("Status: active", constraints)
            self.assertIn("- user-confirmed", constraints)

            self.assertEqual(
                main([
                    "add", "The parser may require JSON.", "--type", "constraint",
                    "--candidate", "--evidence", "agent-observed", "--project-root", tmp,
                ]),
                0,
            )
            inbox = (memory / "inbox.md").read_text(encoding="utf-8")
            self.assertIn("Status: candidate", inbox)
            self.assertIn("Candidate-Type: constraint", inbox)
            self.assertEqual(count_inbox_items(inbox), 1)
            self.assertNotIn("The parser may require JSON", (memory / "constraints.md").read_text(encoding="utf-8"))

            supersede_args = [
                "add", "Allow an explicit offline exception.", "--type", "constraint",
                "--supersedes", old_id, "--evidence", "user-confirmed",
                "--project-root", tmp,
            ]
            supersede_plan = preview_id(supersede_args)
            self.assertEqual(
                main([*supersede_args, "--apply", "--confirm-plan", supersede_plan]),
                0,
            )
            constraints = (memory / "constraints.md").read_text(encoding="utf-8")
            self.assertIn("Status: superseded", constraints)
            self.assertIn(f"Supersedes: {old_id}", constraints)
            self.assertIn("Superseded-By: MC-CON-", constraints)

    def test_plan_id_is_deterministic_and_changes_with_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.md"
            path.write_text("one\n", encoding="utf-8")
            plan = MutationPlan("test", {}, str(uuid.uuid4()), "0.6", (TextMutation(path, "two\n"),))
            first = plan.plan_id
            self.assertEqual(first, plan.plan_id)
            path.write_text("changed\n", encoding="utf-8")
            self.assertNotEqual(first, plan.plan_id)

    def test_stale_forget_plan_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "constraints.md").write_text("# Constraints\n\n- Remove Alpha.\n", encoding="utf-8")
            plan_id = preview_id(["forget", "Alpha", "--mode", "soft", "--project-root", tmp])
            (memory / "constraints.md").write_text("# Constraints\n\n- Remove Alpha.\n- Concurrent edit.\n", encoding="utf-8")
            before = (memory / "constraints.md").read_text(encoding="utf-8")
            err = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(err):
                code = main([
                    "forget", "Alpha", "--mode", "soft", "--apply",
                    "--confirm-plan", plan_id, "--project-root", tmp,
                ])
            self.assertEqual(code, 2)
            self.assertEqual((memory / "constraints.md").read_text(encoding="utf-8"), before)

    def test_compact_and_forget_rebuild_complete_plan_under_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            inbox = memory / "inbox.md"
            inbox.write_text("# Memory Inbox\n\n- Duplicate\n- Duplicate\n", encoding="utf-8")
            compact_args = ["compact", "--project-root", tmp]
            compact_plan = preview_id(compact_args)
            with patch(
                "memory_custodian.compact._inbox_cleanup_mutations",
                wraps=compact_module._inbox_cleanup_mutations,
            ) as rebuilt:
                self.assertEqual(
                    main([*compact_args, "--apply", "--confirm-plan", compact_plan]),
                    0,
                )
            self.assertEqual(rebuilt.call_count, 2)

            (memory / "constraints.md").write_text(
                "# Constraints\n\n- Remove Alpha.\n",
                encoding="utf-8",
            )
            forget_args = ["forget", "Alpha", "--mode", "soft", "--project-root", tmp]
            forget_plan = preview_id(forget_args)
            with patch(
                "memory_custodian.forget._build_forget_mutation_plan",
                wraps=forget_module._build_forget_mutation_plan,
            ) as rebuilt:
                self.assertEqual(
                    main([*forget_args, "--apply", "--confirm-plan", forget_plan]),
                    0,
                )
            self.assertEqual(rebuilt.call_count, 2)

    def test_nested_memory_dir_plans_are_repo_relative_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_name = "docs/team/memory"
            memory = Path(tmp) / memory_name
            self.assertEqual(
                main(
                    [
                        "init",
                        "--project-root",
                        tmp,
                        "--memory-dir",
                        memory_name,
                    ]
                ),
                0,
            )
            inbox = memory / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n- Duplicate\n- Duplicate\n",
                encoding="utf-8",
            )
            compact_args = [
                "compact",
                "--project-root",
                tmp,
                "--memory-dir",
                memory_name,
            ]
            compact_plan, compact_output = preview(compact_args)
            self.assertIn("docs/team/memory/inbox.md", compact_output)
            self.assertNotIn("\n- team/memory/inbox.md", compact_output)
            self.assertEqual(
                main(
                    [
                        *compact_args,
                        "--apply",
                        "--confirm-plan",
                        compact_plan,
                    ]
                ),
                0,
            )
            self.assertEqual(inbox.read_text(encoding="utf-8").count("- Duplicate"), 1)

            self.assertEqual(
                main(
                    [
                        "add",
                        "NestedMemoryMarker",
                        "--type",
                        "constraint",
                        "--project-root",
                        tmp,
                        "--memory-dir",
                        memory_name,
                    ]
                ),
                0,
            )
            forget_args = [
                "forget",
                "NestedMemoryMarker",
                "--mode",
                "soft",
                "--project-root",
                tmp,
                "--memory-dir",
                memory_name,
            ]
            forget_plan, forget_output = preview(forget_args)
            self.assertIn("docs/team/memory/constraints.md", forget_output)
            self.assertNotIn("\n- team/memory/constraints.md", forget_output)
            self.assertEqual(
                main(
                    [
                        *forget_args,
                        "--apply",
                        "--confirm-plan",
                        forget_plan,
                    ]
                ),
                0,
            )
            self.assertNotIn(
                "NestedMemoryMarker",
                (memory / "constraints.md").read_text(encoding="utf-8"),
            )

    def test_lock_acquire_release_timeout_and_stale(self):
        with tempfile.TemporaryDirectory() as state, patch.dict(os.environ, {"XDG_STATE_HOME": state}):
            project_id = str(uuid.uuid4())
            root = Path(state)
            with mutation_lock(project_id, root, "test", timeout=0.1):
                self.assertTrue(lock_path(project_id).exists())
                with self.assertRaises(LockError):
                    with mutation_lock(project_id, root, "other", timeout=0):
                        pass
            self.assertFalse(lock_path(project_id).exists())
            path = lock_path(project_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"hostname": socket.gethostname(), "pid": 99999999}),
                encoding="utf-8",
            )
            old = time.time() - 61
            os.utime(path, (old, old))
            self.assertTrue(stale_lock(path))

    def test_malformed_lock_requires_age_and_explicit_stale_recovery(self):
        with tempfile.TemporaryDirectory() as state, patch.dict(
            os.environ,
            {"XDG_STATE_HOME": state},
        ):
            project_id = str(uuid.uuid4())
            root = Path(state)
            path = lock_path(project_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"pid":', encoding="utf-8")
            fresh = time.time() - MALFORMED_LOCK_RECOVERY_AGE_SECONDS + 10
            os.utime(path, (fresh, fresh))
            self.assertFalse(stale_lock(path))
            with self.assertRaises(LockError):
                with mutation_lock(
                    project_id,
                    root,
                    "without recovery",
                    timeout=0,
                ):
                    pass

            old = time.time() - MALFORMED_LOCK_RECOVERY_AGE_SECONDS - 1
            os.utime(path, (old, old))
            self.assertTrue(stale_lock(path))
            with mutation_lock(
                project_id,
                root,
                "recover malformed",
                timeout=0.1,
                break_stale=True,
            ):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["pid"], os.getpid())
            self.assertFalse(path.exists())

    def test_pending_preview_seed_ttl_removes_old_and_preserves_fresh(self):
        with tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as project:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                _old_value, old_path = pending_project_id(
                    "ttl-old",
                    Path(project),
                    "old-source",
                )
                old = time.time() - PENDING_PLAN_MAX_AGE_SECONDS - 1
                os.utime(old_path, (old, old))

                _fresh_value, fresh_path = pending_project_id(
                    "ttl-fresh",
                    Path(project),
                    "fresh-source",
                )
                self.assertFalse(old_path.exists())
                self.assertTrue(fresh_path.exists())

    def test_scans_redact_secret_and_locate_machine_path(self):
        path = Path("docs/memory/preferences.md")
        findings = scan_text(
            path,
            "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz\nPath /Users/alice/private/project\n",
        )
        self.assertTrue(any(item.category == "security" for item in findings))
        self.assertTrue(any(item.kind == "machine-path" for item in findings))
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", " ".join(item.preview for item in findings))

    def test_check_flags_redacted_security_and_privacy_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nAudit fixture.\n\n"
                "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz\n"
                "Local path: /Users/alice/private/project\n",
                encoding="utf-8",
            )
            normal = StringIO()
            with redirect_stdout(normal):
                normal_code = main(["check", "--project-root", tmp])
            self.assertEqual(normal_code, 1)
            self.assertIn("run `memory-custodian check --security`", normal.getvalue())
            self.assertIn("run `memory-custodian check --privacy`", normal.getvalue())
            self.assertNotIn("brief.md:6", normal.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                code = main(["check", "--security", "--privacy", "--project-root", tmp])
            text = output.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("brief.md:6", text)
            self.assertIn("Security findings:", text)
            self.assertIn("Privacy findings:", text)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz", text)

    def test_near_limit_is_reported_and_generates_dry_run_maintenance_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nBudget trigger fixture.\n",
                encoding="utf-8",
            )
            decisions = memory / "decisions.md"
            decisions.write_text(
                "# Decisions\n\n" + " ".join("context" for _ in range(640)) + "\n",
                encoding="utf-8",
            )
            self.assertGreaterEqual(estimate_tokens(decisions.read_text(encoding="utf-8")), 640)

            added = StringIO()
            with redirect_stdout(added):
                self.assertEqual(
                    main([
                        "add", "Keep maintenance previews non-destructive.", "--type", "decision",
                        "--evidence", "user-confirmed", "--project-root", tmp,
                    ]),
                    0,
                )
            add_text = added.getvalue()
            self.assertIn("State: NEAR LIMIT", add_text)
            self.assertIn("Generating maintenance preview", add_text)
            self.assertIn("Maintenance preview (dry run; no files changed)", add_text)
            self.assertIn("memory-custodian compact --target decisions.md", add_text)

            status = StringIO()
            with redirect_stdout(status):
                self.assertEqual(main(["status", "--project-root", tmp]), 1)
            self.assertIn("decisions.md: NEAR LIMIT", status.getvalue())

            checked = StringIO()
            with redirect_stdout(checked):
                self.assertEqual(main(["check", "--project-root", tmp]), 0)
            self.assertIn("decisions.md: near limit", checked.getvalue())

            compacted = StringIO()
            with redirect_stdout(compacted):
                self.assertEqual(
                    main(["compact", "--target", "decisions.md", "--project-root", tmp]),
                    0,
                )
            self.assertIn("State: NEAR LIMIT", compacted.getvalue())
            self.assertIn("Maintenance preview (dry run; no files changed)", compacted.getvalue())

    def test_identical_legacy_projects_receive_distinct_random_project_ids(self):
        legacy_manifest = (
            "# Memory Manifest\n\n"
            "## Always load\n"
            "- brief.md\n\n"
            "## Load by task\n\n"
            "### Planning / architecture / refactoring\n"
            "Load:\n"
            "- decisions.md\n"
            "- constraints.md\n"
            "- do-not-use.md\n\n"
            "## Explicit only\n"
            "- archive/\n\n"
            "## Optional rules\n"
            "- rules/\n\n"
            "## Optional profiles\n"
            "- profiles/\n"
        )
        with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as state:
            roots = [Path(parent) / "one", Path(parent) / "two"]
            for root in roots:
                memory = root / "docs" / "memory"
                memory.mkdir(parents=True)
                (memory / "manifest.md").write_text(legacy_manifest, encoding="utf-8")

            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                for root in roots:
                    args = ["migrate", "--project-root", str(root)]
                    plan_id = preview_id(args)
                    self.assertEqual(
                        main([*args, "--apply", "--confirm-plan", plan_id]),
                        0,
                    )

            project_ids = []
            for root in roots:
                text = (root / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8")
                project_ids.append(re.search(r"project_id: ([0-9a-f-]+)", text).group(1))
            self.assertNotEqual(project_ids[0], project_ids[1])
            self.assertTrue(all(uuid.UUID(value).version == 4 for value in project_ids))

    def test_migrate_converts_clear_area_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(
                main([
                    "add", "Temporary area setup.", "--type", "area", "--name", "backend",
                    "--evidence", "user-confirmed", "--project-root", tmp,
                ]),
                0,
            )
            memory = Path(tmp) / "docs" / "memory"
            manifest = memory / "manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "- protocol_version: 0.6", "- protocol_version: 0.5"
                ),
                encoding="utf-8",
            )
            area = memory / "areas" / "backend.md"
            area.write_text(
                "# Area: backend\n\n"
                "## 2026-07-28 - Keep backend offline\n"
                "Decision:\nUse only local storage.\n",
                encoding="utf-8",
            )
            args = ["migrate", "--project-root", tmp]
            plan_id = preview_id(args)
            self.assertEqual(main([*args, "--apply", "--confirm-plan", plan_id]), 0)
            migrated = area.read_text(encoding="utf-8")
            self.assertRegex(migrated, r"MC-AREA-20260728-[0-9a-f]{8}")
            self.assertIn("Scope: area:backend", migrated)
            self.assertIn("- legacy-unverified", migrated)

    def test_real_concurrent_add_preserves_both_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            first_args = _subject_for_add([
                "add", "Decision A", "--type", "decision", "--evidence", "user-confirmed",
                "--project-root", tmp,
            ])
            second_args = _subject_for_add([
                "add", "Decision B", "--type", "decision", "--evidence", "user-confirmed",
                "--project-root", tmp,
            ])
            command = [sys.executable, "-m", "memory_custodian.main"]
            first = subprocess.Popen([*command, *first_args], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            second = subprocess.Popen([*command, *second_args], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out_a, err_a = first.communicate(timeout=15)
            out_b, err_b = second.communicate(timeout=15)
            self.assertEqual((first.returncode, second.returncode), (0, 0), (out_a, err_a, out_b, err_b))
            decisions = (Path(tmp) / "docs" / "memory" / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("Decision A", decisions)
            self.assertIn("Decision B", decisions)

    def test_real_concurrent_protocol_05_add_uses_bootstrap_guard(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest_path = Path(tmp) / "docs" / "memory" / "manifest.md"
            legacy_manifest = manifest_path.read_text(encoding="utf-8")
            legacy_manifest = legacy_manifest.replace(
                "- protocol_version: 0.6",
                "- protocol_version: 0.5",
            )
            legacy_manifest = re.sub(
                r"(?m)^- project_id: [0-9a-f-]+\n",
                "",
                legacy_manifest,
            )
            manifest_path.write_text(legacy_manifest, encoding="utf-8")

            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            env["XDG_STATE_HOME"] = state
            command = [sys.executable, "-m", "memory_custodian.main", "add"]
            first = subprocess.Popen(
                [
                    *command,
                    "Legacy concurrent A",
                    "--type",
                    "decision",
                    "--project-root",
                    tmp,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            second = subprocess.Popen(
                [
                    *command,
                    "Legacy concurrent B",
                    "--type",
                    "decision",
                    "--project-root",
                    tmp,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output_a = first.communicate(timeout=15)
            output_b = second.communicate(timeout=15)
            self.assertEqual(
                (first.returncode, second.returncode),
                (0, 0),
                (output_a, output_b),
            )
            decisions = (
                Path(tmp) / "docs" / "memory" / "decisions.md"
            ).read_text(encoding="utf-8")
            self.assertIn("Legacy concurrent A", decisions)
            self.assertIn("Legacy concurrent B", decisions)

    def test_real_lock_timeout_and_guarded_stale_break(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = (Path(tmp) / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8")
                project_id = re.search(r"project_id: ([0-9a-f-]+)", manifest).group(1)
                env = dict(os.environ)
                env["PYTHONPATH"] = str(ROOT / "cli")
                env["XDG_STATE_HOME"] = state
                add_args = _subject_for_add([
                    "add", "Blocked",
                    "--type", "decision", "--evidence", "user-confirmed",
                    "--lock-timeout", "0", "--project-root", tmp,
                ])
                command = [sys.executable, "-m", "memory_custodian.main", *add_args]
                with mutation_lock(project_id, Path(tmp), "holder"):
                    blocked = subprocess.run(command, env=env, text=True, capture_output=True)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn("Timed out waiting for mutation lock", blocked.stderr)

                path = lock_path(project_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"hostname": socket.gethostname(), "pid": 99999999}),
                    encoding="utf-8",
                )
                old = time.time() - 61
                os.utime(path, (old, old))
                recovered = subprocess.run(
                    [*command[:-4], "--break-stale-lock", *command[-4:]],
                    env=env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_add_and_compact_do_not_silently_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            inbox = Path(tmp) / "docs" / "memory" / "inbox.md"
            inbox.write_text("# Memory Inbox\n\n- Duplicate\n- Duplicate\n", encoding="utf-8")
            plan_id = preview_id(["compact", "--project-root", tmp])
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            add = subprocess.Popen(
                [
                    sys.executable, "-m", "memory_custodian.main", "add", "Concurrent candidate",
                    "--type", "constraint", "--candidate", "--evidence", "agent-observed",
                    "--project-root", tmp,
                ],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            compact = subprocess.Popen(
                [
                    sys.executable, "-m", "memory_custodian.main", "compact", "--apply",
                    "--confirm-plan", plan_id, "--project-root", tmp,
                ],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            add.communicate(timeout=15)
            compact.communicate(timeout=15)
            self.assertEqual(add.returncode, 0)
            self.assertIn(compact.returncode, {0, 2})
            text = inbox.read_text(encoding="utf-8")
            self.assertIn("Concurrent candidate", text)
            self.assertTrue(text.startswith("# Memory Inbox"))


if __name__ == "__main__":
    unittest.main()
