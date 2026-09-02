from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import hashlib
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

from memory_custodian.locking import stale_lock
from memory_custodian.locking import bootstrap_lock_id, lock_path
from memory_custodian.main import main
from memory_custodian.protocol import parse_manifest_task_modules
from memory_custodian.read import _optional_requested
from memory_custodian.routes import RouteReason, RoutedModule, merge_routed_modules
from memory_custodian.scanning import scan_text
from memory_custodian import enable as enable_module
from memory_custodian import init as init_module
from memory_custodian.subjects import (
    generate_subject_id,
    normalize_alias,
    normalize_canonical_ref,
)


ROOT = Path(__file__).resolve().parents[1]


def preview(argv: list[str]) -> tuple[str, str]:
    output = StringIO()
    with redirect_stdout(output):
        code = main(argv)
    if code != 0:
        raise AssertionError(output.getvalue())
    match = re.search(r"Plan ID: ([0-9a-f]{16})", output.getvalue())
    if not match:
        raise AssertionError(output.getvalue())
    return match.group(1), output.getvalue()


def apply_preview(argv: list[str]) -> str:
    plan_id, _text = preview(argv)
    output = StringIO()
    with redirect_stdout(output):
        code = main([*argv, "--apply", "--confirm-plan", plan_id])
    if code != 0:
        raise AssertionError(output.getvalue())
    return output.getvalue()


def add_subject(root: str, title: str, *, canonical_ref: str | None = None, alias: str | None = None) -> str:
    args = [
        "subject", "add", title,
        "--kind", "dependency" if canonical_ref and canonical_ref.startswith("dependency:") else "concept",
        "--evidence", "user-confirmed",
        "--project-root", root,
    ]
    if canonical_ref:
        args.extend(["--canonical-ref", canonical_ref])
    if alias:
        args.extend(["--alias", alias])
    apply_preview(args)
    text = (Path(root) / "docs" / "memory" / "subjects.md").read_text(encoding="utf-8")
    return re.search(rf"(?m)^## (MC-SUBJ-[^\s]+) — {re.escape(title)}$", text).group(1)


class SubjectRegistryTests(unittest.TestCase):
    def test_init_creates_non_routed_subject_registry_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            self.assertTrue((memory / "subjects.md").exists())
            manifest = (memory / "manifest.md").read_text(encoding="utf-8")
            self.assertIn("- subject_schema_version: 1", manifest)
            self.assertIn("- subject_registry: subjects.md", manifest)
            self.assertIn("- conflict_policy: canonical-subject-and-review", manifest)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(["read", "--task", "implementation", "--names-only", "--project-root", tmp]),
                    0,
                )
            self.assertNotIn("- subjects.md", output.getvalue())

    def test_subject_normalization_collision_and_rename_preserve_id(self):
        self.assertRegex(generate_subject_id(), r"^MC-SUBJ-\d{8}-[0-9a-f]{8}$")
        self.assertEqual(normalize_alias("  LIBRARY   X  "), "library x")
        self.assertEqual(
            normalize_canonical_ref("dependency:pypi:Library_X"),
            "dependency:pypi:library-x",
        )
        self.assertEqual(
            normalize_canonical_ref("repo-path:src\\storage"),
            "repo-path:src/storage",
        )
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            subject_id = add_subject(
                tmp,
                "Library X",
                canonical_ref="dependency:pypi:Library_X",
                alias="libx",
            )
            err = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(err):
                code = main([
                    "subject", "add", "Different display",
                    "--kind", "dependency",
                    "--canonical-ref", "dependency:pypi:library.x",
                    "--evidence", "user-confirmed",
                    "--project-root", tmp,
                ])
            self.assertEqual(code, 2)
            self.assertIn(subject_id, err.getvalue())

            apply_preview([
                "subject", "rename", subject_id, "Library X Runtime",
                "--project-root", tmp,
            ])
            subjects = (Path(tmp) / "docs" / "memory" / "subjects.md").read_text(encoding="utf-8")
            self.assertIn(f"## {subject_id} — Library X Runtime", subjects)
            self.assertIn("- Library X", subjects)
            apply_preview([
                "subject", "add-alias", subject_id, "library-runtime",
                "--project-root", tmp,
            ])
            shown = StringIO()
            with redirect_stdout(shown):
                self.assertEqual(
                    main(["subject", "show", subject_id, "--project-root", tmp]),
                    0,
                )
            self.assertIn("- library-runtime", shown.getvalue())
            self.assertIn("Referenced by:\n- none", shown.getvalue())

    def test_active_subject_facet_admission_conflict_and_supersede(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            subject_id = add_subject(tmp, "Runtime policy")
            missing = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(missing):
                self.assertEqual(
                    main([
                        "add", "Missing governed identity.",
                        "--type", "decision",
                        "--evidence", "user-confirmed",
                        "--project-root", tmp,
                    ]),
                    2,
                )
            self.assertIn("requires both --subject", missing.getvalue())
            invalid = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(invalid):
                self.assertEqual(
                    main([
                        "add", "Invalid Facet.",
                        "--type", "decision",
                        "--subject", subject_id,
                        "--facet", "made-up",
                        "--evidence", "user-confirmed",
                        "--project-root", tmp,
                    ]),
                    2,
                )
            self.assertIn("Facet 'made-up' is not valid", invalid.getvalue())
            base = [
                "--type", "decision",
                "--subject", subject_id,
                "--facet", "version-policy",
                "--evidence", "user-confirmed",
                "--project-root", tmp,
            ]
            self.assertEqual(main(["add", "Support Python 3.10.", *base]), 0)
            decisions = (Path(tmp) / "docs" / "memory" / "decisions.md").read_text(encoding="utf-8")
            old_id = re.search(r"## (MC-DEC-[^\s]+)", decisions).group(1)
            err = StringIO()
            with redirect_stderr(err):
                self.assertEqual(main(["add", "Support Python 3.11.", *base]), 2)
            self.assertIn("Active structural owner already exists", err.getvalue())

            apply_preview([
                "add", "Support Python 3.11.", *base,
                "--supersedes", old_id,
            ])
            decisions = (Path(tmp) / "docs" / "memory" / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("Status: superseded", decisions)
            self.assertIn(f"Supersedes: {old_id}", decisions)
            check = StringIO()
            with redirect_stdout(check):
                self.assertEqual(main(["check", "--project-root", tmp]), 1)
            self.assertIn("generated scaffold", check.getvalue())

    def test_purge_refuses_to_remove_referenced_subject_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            subject_id = add_subject(tmp, "Sensitive subject")
            self.assertEqual(
                main([
                    "add", "Keep the implementation constraint abstract.",
                    "--type", "constraint",
                    "--subject", subject_id,
                    "--facet", "security",
                    "--evidence", "user-confirmed",
                    "--project-root", tmp,
                ]),
                0,
            )
            args = [
                "forget", "Sensitive subject",
                "--mode", "purge",
                "--allow-broad-match",
                "--project-root", tmp,
            ]
            plan_id, output = preview(args)
            self.assertIn("cannot remove MC-SUBJ-", output)
            before = (Path(tmp) / "docs" / "memory" / "subjects.md").read_text(encoding="utf-8")
            applied = StringIO()
            with redirect_stdout(applied):
                self.assertEqual(
                    main([*args, "--apply", "--confirm-plan", plan_id]),
                    1,
                )
            self.assertIn("Refusing apply", applied.getvalue())
            self.assertEqual(
                (Path(tmp) / "docs" / "memory" / "subjects.md").read_text(encoding="utf-8"),
                before,
            )


class ErasureAndRoutingTests(unittest.TestCase):
    def _fixture(self, root: str) -> Path:
        self.assertEqual(main(["init", "--project-root", root]), 0)
        memory = Path(root) / "docs" / "memory"
        (memory / "brief.md").write_text("# Project Brief\n\nPurpose:\nErasure tests.\n", encoding="utf-8")
        (memory / "decisions.md").write_text(
            "# Decisions\n\n## Legacy removable\nDecision:\nSensitiveTopic is enabled.\n",
            encoding="utf-8",
        )
        archive = memory / "archive"
        archive.mkdir()
        (archive / "decisions-old.md").write_text(
            "# Archive\n\n## Old removable\nDecision:\nSensitiveTopic was enabled.\n",
            encoding="utf-8",
        )
        return memory

    def test_erasure_scope_matrix_and_apply_boundary(self):
        for mode, archive_expected, retain_expected in (
            ("soft", "no", "yes"),
            ("hard", "no", "no"),
            ("purge", "yes", "no"),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                self._fixture(tmp)
                args = ["forget", "SensitiveTopic", "--mode", mode, "--project-root", tmp]
                if mode == "purge":
                    args.append("--allow-broad-match")
                plan_id, output = preview(args)
                self.assertIn("Removal scope:", output)
                self.assertIn("- Active managed memory: yes", output)
                self.assertIn(f"- Managed archive: {archive_expected}", output)
                self.assertIn(f"- New tombstones/logs retain topic: {retain_expected}", output)
                self.assertIn("- Git history modified: no", output)
                self.assertIn("- Existing clones, forks and backups revoked: no", output)
                if mode in {"hard", "purge"}:
                    diagnostics = output.replace("SensitiveTopic", "", 1)
                    self.assertNotIn("SensitiveTopic", diagnostics)
                applied = StringIO()
                with redirect_stdout(applied):
                    self.assertEqual(
                        main([*args, "--apply", "--confirm-plan", plan_id]),
                        0,
                    )
                self.assertIn("Removed from the selected managed memory scope.", applied.getvalue())
                self.assertIn(
                    "Git history and previously distributed copies were not modified.",
                    applied.getvalue(),
                )

    def test_routing_provenance_identity_and_privacy_location(self):
        manifest = """# Memory Manifest

## Always load
- brief.md

## Load by task

### Planning / architecture / refactoring
Load:
- decisions.md

### Implementation / execution / debugging
Load:
- constraints.md

### User-facing artifact / output
Load:
- do-not-use.md

### Preferences
Load:
- preferences.md

### Change history / recap
Load:
- changelog.md

### Memory maintenance
Load:
- inbox.md
"""
        modules = parse_manifest_task_modules(manifest, "planning")
        modules = merge_routed_modules([
            *modules,
            RoutedModule("brief.md", True, (RouteReason.CANONICAL_TASK,)),
        ])
        self.assertEqual(modules[0].module_id, "brief.md")
        self.assertEqual(
            modules[0].reasons,
            (RouteReason.ALWAYS_LOAD, RouteReason.CANONICAL_TASK),
        )
        explicit = merge_routed_modules([
            *modules,
            *_optional_requested("profiles", ["git"]),
            *_optional_requested("areas", ["storage"]),
        ])
        self.assertIn(RouteReason.EXPLICIT_PROFILE, explicit[-2].reasons)
        self.assertIn(RouteReason.EXPLICIT_AREA, explicit[-1].reasons)
        absent = explicit[-1].with_result(loaded=False, absent=True)
        self.assertIn(RouteReason.OPTIONAL_ABSENT, absent.reasons)
        omitted = modules[0].with_result(loaded=True, omitted_entries=2)
        self.assertIn(RouteReason.BUDGET_OMISSION, omitted.reasons)

        findings = scan_text(Path("preferences.md"), "Use /Volumes/Local/Xcode.app")
        self.assertEqual(findings[0].kind, "machine-path")

    def test_same_version_migrate_adds_subject_schema_without_changing_project_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            manifest_path = memory / "manifest.md"
            manifest = manifest_path.read_text(encoding="utf-8")
            project_id = re.search(r"project_id: ([0-9a-f-]+)", manifest).group(1)
            for line in (
                "- subject_schema_version: 1\n",
                "- subject_registry: subjects.md\n",
                "- conflict_identity_policy: scope-subject-facet\n",
            ):
                manifest = manifest.replace(line, "")
            manifest_path.write_text(manifest, encoding="utf-8")
            (memory / "subjects.md").unlink()
            apply_preview(["migrate", "--project-root", tmp])
            migrated = manifest_path.read_text(encoding="utf-8")
            self.assertIn(f"- project_id: {project_id}", migrated)
            self.assertIn("- subject_schema_version: 1", migrated)
            self.assertTrue((memory / "subjects.md").exists())

    def test_real_abnormal_exit_lock_is_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            env["XDG_STATE_HOME"] = state
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = (Path(tmp) / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8")
            project_id = re.search(r"project_id: ([0-9a-f-]+)", manifest).group(1)
            crashed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os; from pathlib import Path; "
                        "from memory_custodian.locking import mutation_lock; "
                        f"c=mutation_lock('{project_id}', Path({tmp!r}), 'crash'); "
                        "c.__enter__(); os._exit(7)"
                    ),
                ],
                env=env,
            )
            self.assertEqual(crashed.returncode, 7)
            path = Path(state) / "memory-custodian" / "locks" / f"{project_id}.lock"
            self.assertTrue(path.exists())
            old = time.time() - 61
            os.utime(path, (old, old))
            self.assertTrue(stale_lock(path))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["hostname"], socket.gethostname())


class AuditGapRegressionTests(unittest.TestCase):
    def test_repair_installs_the_guard_project_identity_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest_path = Path(tmp) / "docs" / "memory" / "manifest.md"
            manifest_path.write_text(
                re.sub(
                    r"(?m)^- project_id: [0-9a-f-]+\n",
                    "",
                    manifest_path.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            guard_id = uuid.UUID("12345678-1234-4234-8234-123456789abc")
            real_manifest_repair = init_module.manifest_with_current_protocol_metadata
            observed_ids = []

            def verify_guard_identity(text, *, project_id):
                observed_ids.append(project_id)
                self.assertTrue(
                    lock_path(bootstrap_lock_id(Path(tmp))).exists()
                )
                self.assertTrue(lock_path(project_id).exists())
                return real_manifest_repair(text, project_id=project_id)

            with patch.dict(os.environ, {"XDG_STATE_HOME": state}), patch(
                "memory_custodian.locking.uuid.uuid4",
                return_value=guard_id,
            ), patch(
                "memory_custodian.init.manifest_with_current_protocol_metadata",
                side_effect=verify_guard_identity,
            ):
                self.assertEqual(
                    main(["init", "--repair", "--project-root", tmp]),
                    0,
                )
            self.assertEqual(observed_ids, [str(guard_id)])
            repaired = manifest_path.read_text(encoding="utf-8")
            self.assertEqual(
                re.findall(r"(?m)^- project_id: ([0-9a-f-]+)$", repaired),
                [str(guard_id)],
            )

    def test_enable_holds_bootstrap_and_permanent_project_locks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                root = Path(tmp)
                manifest = (
                    root / "docs" / "memory" / "manifest.md"
                ).read_text(encoding="utf-8")
                project_id = re.search(
                    r"(?m)^- project_id: ([0-9a-f-]+)$",
                    manifest,
                ).group(1)
                real_apply = enable_module.apply_mutations

                def verify_locks(mutations):
                    self.assertTrue(lock_path(bootstrap_lock_id(root)).exists())
                    self.assertTrue(lock_path(project_id).exists())
                    return real_apply(mutations)

                with patch(
                    "memory_custodian.enable.apply_mutations",
                    side_effect=verify_locks,
                ):
                    self.assertEqual(
                        main(["enable", "preferences", "--project-root", tmp]),
                        0,
                    )

    def test_enable_concurrency_preserves_both_index_updates(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            env["XDG_STATE_HOME"] = state
            command = [sys.executable, "-m", "memory_custodian.main", "enable"]
            first = subprocess.Popen(
                [*command, "profile/git", "--project-root", tmp],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            second = subprocess.Popen(
                [*command, "area/storage", "--project-root", tmp],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            first_output = first.communicate(timeout=15)
            second_output = second.communicate(timeout=15)
            self.assertEqual(
                (first.returncode, second.returncode),
                (0, 0),
                (first_output, second_output),
            )
            manifest = (
                Path(tmp) / "docs" / "memory" / "manifest.md"
            ).read_text(encoding="utf-8")
            self.assertIn("`profiles/git.md`", manifest)
            self.assertIn("`areas/storage.md`", manifest)

    def test_concurrent_first_init_uses_one_bootstrap_identity(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "cli")
            env["XDG_STATE_HOME"] = state
            command = [
                sys.executable,
                "-m",
                "memory_custodian.main",
                "init",
                "--project-root",
                tmp,
            ]
            first = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            second = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            first_output = first.communicate(timeout=15)
            second_output = second.communicate(timeout=15)
            self.assertEqual(
                (first.returncode, second.returncode),
                (0, 0),
                (first_output, second_output),
            )
            manifest = (
                Path(tmp) / "docs" / "memory" / "manifest.md"
            ).read_text(encoding="utf-8")
            ids = re.findall(r"(?m)^- project_id: ([0-9a-f-]+)$", manifest)
            self.assertEqual(len(ids), 1)
            self.assertFalse(lock_path(bootstrap_lock_id(Path(tmp))).exists())

    def test_first_init_holds_bootstrap_and_project_locks_while_writing(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            root = Path(tmp)
            real_apply = init_module.apply_mutations

            def verify_locks(mutations):
                manifest_mutation = next(
                    mutation for mutation in mutations if mutation.path.name == "manifest.md"
                )
                project_id = re.search(
                    r"project_id: ([0-9a-f-]+)",
                    manifest_mutation.text,
                ).group(1)
                self.assertTrue(lock_path(bootstrap_lock_id(root)).exists())
                self.assertTrue(lock_path(project_id).exists())
                return real_apply(mutations)

            with patch.dict(os.environ, {"XDG_STATE_HOME": state}), patch(
                "memory_custodian.init.apply_mutations",
                side_effect=verify_locks,
            ):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)

    def test_scan_preview_redacts_all_sensitive_values_on_line(self):
        first = "FirstSecretValue123"
        second = "SecondSecretValue456"
        findings = scan_text(
            Path("constraints.md"),
            f"api_key={first} password={second}",
        )
        self.assertGreaterEqual(len(findings), 1)
        for finding in findings:
            self.assertNotIn(first, finding.preview)
            self.assertNotIn(second, finding.preview)
            self.assertIn("[redacted]", finding.preview)

    def test_check_revalidates_evidence_and_provisional_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            subject_id = add_subject(tmp, "Evidence subject")
            memory = Path(tmp) / "docs" / "memory"
            (memory / "constraints.md").write_text(
                "# Constraints\n\n"
                "## MC-CON-20260729-a1b2c3d4 — Invalid evidence\n\n"
                "Status: active\n"
                "Scope: project\n"
                f"Subject: {subject_id}\n"
                "Facet: security\n"
                "Evidence:\n"
                "- arbitrary-value\n\n"
                "Constraint:\nKeep validation strict.\n",
                encoding="utf-8",
            )
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n"
                "## MC-INBOX-20260729-b2c3d4e5 — Candidate\n\n"
                "Status: candidate\n"
                "Candidate-Type: constraint\n"
                "Scope: project\n"
                "Provisional-Subject: MC-SUBJ-20260729-deadbeef\n"
                "Provisional-Facet: security\n"
                "Evidence:\n"
                "- agent-observed\n\n"
                "Statement:\nReview later.\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["check", "--project-root", tmp]), 1)
            text = output.getvalue()
            self.assertIn("has invalid Evidence", text)
            self.assertNotIn("arbitrary-value", text)
            self.assertIn("missing or inactive Provisional-Subject", text)

    def test_hard_forget_uses_random_pending_tombstone_suffix(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            topic = "DictionaryAttackTopic"
            (memory / "decisions.md").write_text(
                f"# Decisions\n\n## Removable\nDecision:\n{topic} is enabled.\n",
                encoding="utf-8",
            )
            manifest = (memory / "manifest.md").read_text(encoding="utf-8")
            project_id = re.search(r"project_id: ([0-9a-f-]+)", manifest).group(1)
            old_suffix = hashlib.sha256(
                f"{project_id}\0hard\0{topic}".encode("utf-8")
            ).hexdigest()[:8]
            args = ["forget", topic, "--mode", "hard", "--project-root", tmp]
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}), patch(
                "memory_custodian.plans.uuid.uuid4",
                return_value=uuid.UUID("12345678-1234-4234-8234-123456789abc"),
            ):
                plan_id, preview_text = preview(args)
                self.assertNotIn(topic, preview_text)
                self.assertNotIn(tmp, preview_text)
                self.assertNotIn("Base SHA-256", preview_text)
                self.assertIn("Digests: redacted for sensitive operation", preview_text)
                applied = StringIO()
                with redirect_stdout(applied):
                    self.assertEqual(
                        main([*args, "--apply", "--confirm-plan", plan_id]),
                        0,
                    )
                self.assertNotIn(topic, applied.getvalue())
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertRegex(
                tombstones,
                r"(?m)^## MC-TOMB-\d{8}-12345678\b",
            )
            self.assertNotRegex(
                tombstones,
                rf"MC-TOMB-\d{{8}}-{re.escape(old_suffix)}\b",
            )
            self.assertNotIn(topic, tombstones)

    def test_purge_blocks_provisional_subject_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            subject_id = add_subject(tmp, "Sensitive candidate subject")
            self.assertEqual(
                main([
                    "add", "Review the abstract policy later.",
                    "--type", "constraint",
                    "--candidate",
                    "--subject", subject_id,
                    "--facet", "security",
                    "--evidence", "agent-observed",
                    "--project-root", tmp,
                ]),
                0,
            )
            args = [
                "forget", "Sensitive candidate subject",
                "--mode", "purge",
                "--allow-broad-match",
                "--project-root", tmp,
            ]
            _plan_id, output = preview(args)
            self.assertIn(f"cannot remove {subject_id.upper()}", output)

    def test_release_notes_have_one_v010_heading(self):
        notes = (ROOT / "RELEASE-NOTES.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^## v0\.10\.0\b", notes)), 1)
        self.assertLess(notes.index("## Unreleased"), notes.index("## v0.10.0"))


if __name__ == "__main__":
    unittest.main()
