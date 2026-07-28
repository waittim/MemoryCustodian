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
from memory_custodian.locking import LockError, lock_path, mutation_lock, stale_lock
from memory_custodian.main import main
from memory_custodian.plans import MutationPlan
from memory_custodian.mutations import TextMutation
from memory_custodian.protocol import count_inbox_items
from memory_custodian.scanning import scan_text


def preview_id(argv: list[str]) -> str:
    output = StringIO()
    with redirect_stdout(output):
        assert main(argv) == 0
    match = re.search(r"Plan ID: ([0-9a-f]{16})", output.getvalue())
    assert match, output.getvalue()
    return match.group(1)


class Protocol06Tests(unittest.TestCase):
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
                main(["add", "Unsupported", "--type", "decision", "--project-root", tmp]),
                2,
            )
            self.assertEqual(
                main([
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
            output = StringIO()
            with redirect_stdout(output):
                code = main(["check", "--security", "--privacy", "--project-root", tmp])
            text = output.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("brief.md:6", text)
            self.assertIn("Security findings:", text)
            self.assertIn("Privacy findings:", text)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz", text)

    def test_real_concurrent_add_preserves_both_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            command = [
                sys.executable, "-m", "memory_custodian.main", "add",
                "--type", "decision", "--evidence", "user-confirmed",
                "--project-root", tmp,
            ]
            first = subprocess.Popen([*command, "Decision A"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            second = subprocess.Popen([*command, "Decision B"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out_a, err_a = first.communicate(timeout=15)
            out_b, err_b = second.communicate(timeout=15)
            self.assertEqual((first.returncode, second.returncode), (0, 0), (out_a, err_a, out_b, err_b))
            decisions = (Path(tmp) / "docs" / "memory" / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("Decision A", decisions)
            self.assertIn("Decision B", decisions)

    def test_real_lock_timeout_and_guarded_stale_break(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = (Path(tmp) / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8")
                project_id = re.search(r"project_id: ([0-9a-f-]+)", manifest).group(1)
                env = dict(os.environ)
                env["PYTHONPATH"] = str(ROOT / "cli")
                env["XDG_STATE_HOME"] = state
                command = [
                    sys.executable, "-m", "memory_custodian.main", "add", "Blocked",
                    "--type", "decision", "--evidence", "user-confirmed",
                    "--lock-timeout", "0", "--project-root", tmp,
                ]
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
