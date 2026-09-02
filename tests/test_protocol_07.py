"""Protocol 0.7 routing, overlay, conflict, ID, and migration coverage."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.main import main
from memory_custodian.routes import glob_matches, parse_optional_module_index


class Protocol07Tests(unittest.TestCase):
    def _capture(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_path_routed_area_requires_scope_and_matches_planned_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main([
                "enable", "area/backend", "--path", "cli/**", "--project-root", tmp,
            ]), 0)
            code, output, _error = self._capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("Routing completeness: INCOMPLETE", output)
            self.assertIn("MC-SKIP-SCOPE-MISSING", self._capture([
                "read", "--task", "implementation", "--explain", "--names-only", "--project-root", tmp,
            ])[1])

            code, output, _error = self._capture([
                "read", "--task", "implementation", "--strict-routing", "--explain",
                "--path", "cli/planned.py", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("cli/planned.py (missing-on-disk)", output)
            self.assertIn("areas/backend.md", output)
            self.assertIn("MC-ROUTE-PATH", output)

    def test_glob_dialect_and_separator_normalization(self):
        self.assertTrue(glob_matches("**/*.py", "root.py"))
        self.assertTrue(glob_matches("**/*.py", "cli/root.py"))
        self.assertTrue(glob_matches("web/**", "web/a/b.ts"))
        self.assertFalse(glob_matches("web/*", "web/a/b.ts"))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "area/backend", "--path", "cli/**", "--project-root", tmp]), 0)
            code, output, _error = self._capture([
                "read", "--task", "implementation", "--path", "cli\\new.py",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("- cli/new.py (missing-on-disk)", output)

    def test_optional_grammar_rejects_duplicate_scalar_and_module(self):
        manifest = """## Optional module index

### Enabled rules
- `rules/output.md`
  - activation: task
  - activation: task-or-explicit
  - tasks: artifact

### Enabled profiles
- None enabled.

### Enabled areas
- None enabled.
"""
        with self.assertRaisesRegex(ValueError, "duplicate optional module key"):
            parse_optional_module_index(manifest)
        duplicate = manifest.replace(
            "  - activation: task-or-explicit\n", ""
        ).replace("\n### Enabled profiles", "\n- `rules/output.md`\n  - activation: explicit-only\n\n### Enabled profiles")
        with self.assertRaisesRegex(ValueError, "duplicate optional module declaration"):
            parse_optional_module_index(duplicate)

    def test_conflict_check_and_strict_read_block_duplicate_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {subject_id} — Storage policy\n\n"
                "Status: active\nKind: concept\nCanonical-Ref: feature:storage-policy\n"
                "Evidence:\n- user-confirmed\n\nAliases:\n- storage policy\n",
                encoding="utf-8",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n"
                f"## MC-CON-20260801-11111111 — First\n\nStatus: active\nScope: project\nSubject: {subject_id}\nFacet: behavior\nEvidence:\n- user-confirmed\n\nConstraint:\nFirst.\n\n"
                f"## MC-CON-20260801-22222222 — Second\n\nStatus: active\nScope: project\nSubject: {subject_id}\nFacet: behavior\nEvidence:\n- user-confirmed\n\nConstraint:\nSecond.\n",
                encoding="utf-8",
            )
            code, output, _error = self._capture(["check", "--conflicts", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("Conflict status: CONFLICT", output)
            self.assertIn("MC-CONFLICT-001", output)
            code, output, _error = self._capture([
                "read", "--task", "implementation", "--strict-routing", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 2)
            self.assertIn("Context pack not approved for substantial work", output)

    def test_local_overlay_requires_binding_and_no_local_excludes_it(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                code, output, _error = self._capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0)
                self.assertIn("UNBOUND", output)
                self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                self.assertEqual(main([
                    "local", "add", "Prefer concise output.", "--type", "preference",
                    "--evidence", "user-confirmed", "--project-root", tmp,
                ]), 0)
                shared = self._capture([
                    "read", "--task", "general", "--no-local", "--project-root", tmp,
                ])[1]
                combined = self._capture([
                    "read", "--task", "general", "--project-root", tmp,
                ])[1]
                self.assertNotIn("Prefer concise output.", shared)
                self.assertIn("Prefer concise output.", combined)
                self.assertIn("Local overlay status: BOUND", combined)

    def test_id_list_show_and_forget_preview_use_canonical_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            code, output, _error = self._capture([
                "add", "Prefer exact examples.", "--type", "preference",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            entry_id = re.search(r"MC-PREF-\d{8}-[0-9a-f]{8}", output).group(0)
            listed = self._capture(["list", "--status", "active", "--project-root", tmp])[1]
            self.assertIn(entry_id, listed)
            shown = self._capture(["show", entry_id, "--project-root", tmp])[1]
            self.assertIn("Source: preferences.md", shown)
            code, preview, _error = self._capture([
                "forget", "--id", entry_id, "--mode", "hard", "--history-check", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("Matched units: 1", preview)
            self.assertIn("History inspection:", preview)
            self.assertIn("Git history modified: no", preview)

    def test_candidate_promotion_is_complete_preview_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            code, output, _error = self._capture([
                "add", "Prefer focused examples.", "--type", "preference", "--candidate",
                "--evidence", "agent-observed", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            candidate_id = re.search(r"MC-INBOX-\d{8}-[0-9a-f]{8}", output).group(0)
            before = (Path(tmp) / "docs/memory/inbox.md").read_text(encoding="utf-8")
            code, preview, _error = self._capture([
                "promote", candidate_id, "--type", "preference",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("New active Entry ID: MC-PREF-", preview)
            self.assertIn(f"Promoted-To: MC-PREF-", preview)
            self.assertIn(f"Promoted-From: {candidate_id}", preview)
            self.assertIn("Target files: inbox.md, preferences.md", preview)
            self.assertIn("Transactional promotion apply requires Protocol 0.8.", preview)
            self.assertEqual((Path(tmp) / "docs/memory/inbox.md").read_text(encoding="utf-8"), before)

    def test_list_uses_stable_references_for_legacy_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            (Path(tmp) / "docs/memory/constraints.md").write_text(
                "# Constraints\n\n- Keep the CLI dependency-free.\n",
                encoding="utf-8",
            )
            code, output, _error = self._capture(["list", "--project-root", tmp])
            self.assertEqual(code, 0)
            self.assertIn("constraints.md#unit-1 [legacy; project]", output)
            self.assertNotRegex(output, r"MC-CON-.*Keep the CLI dependency-free")

    def test_missing_required_module_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            (Path(tmp) / "docs/memory/constraints.md").unlink()
            code, output, _error = self._capture([
                "read", "--task", "implementation", "--explain", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("Routing completeness: INCOMPLETE", output)
            self.assertIn("required-module-missing", output)
            self.assertIn("MC-MISSING-REQUIRED", output)
            strict_code, strict_output, _error = self._capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(strict_code, 1)
            self.assertIn("Context pack not approved for substantial work", strict_output)

    def test_protocol_06_optional_description_migrates_to_explicit_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest_path = Path(tmp) / "docs" / "memory" / "manifest.md"
            manifest = manifest_path.read_text(encoding="utf-8")
            manifest = manifest.replace("protocol_version: 0.7", "protocol_version: 0.6")
            manifest = manifest.replace(
                "### Enabled rules\n- None enabled.",
                "### Enabled rules\n- `rules/output.md`: Keep public output concise.",
            )
            manifest_path.write_text(manifest, encoding="utf-8")
            code, preview, _error = self._capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 0)
            plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", preview).group(1)
            self.assertEqual(main([
                "migrate", "--apply", "--confirm-plan", plan_id, "--project-root", tmp,
            ]), 0)
            migrated = manifest_path.read_text(encoding="utf-8")
            self.assertIn("protocol_version: 0.7", migrated)
            self.assertIn("  - activation: explicit-only", migrated)
            self.assertIn("  - description: Keep public output concise.", migrated)

    def test_path_order_and_duplicates_produce_identical_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main([
                "enable", "area/backend", "--path", "cli/**", "--project-root", tmp,
            ]), 0)
            base = ["read", "--task", "implementation", "--explain", "--names-only", "--project-root", tmp]
            first = self._capture([*base, "--path", "README.md", "--path", "cli/a.py"])[1]
            second = self._capture([*base, "--path", "cli/a.py", "--path", "README.md", "--path", "cli/a.py"])[1]
            self.assertEqual(first, second)

    def test_unbound_copied_project_cannot_read_existing_local_overlay(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", first]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", first]), 0)
                self.assertEqual(main(["local", "link", "--project-root", first]), 0)
                self.assertEqual(main([
                    "local", "add", "Use the first workstation.", "--type", "preference",
                    "--evidence", "user-confirmed", "--project-root", first,
                ]), 0)
                shutil.copytree(Path(first) / "docs", Path(second) / "docs")
                code, output, _error = self._capture([
                    "read", "--task", "general", "--project-root", second,
                ])
                self.assertEqual(code, 0)
                self.assertIn("Local overlay status: UNBOUND", output)
                self.assertNotIn("Use the first workstation.", output)

    def test_corrupt_bound_overlay_marks_routing_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                project_id = re.search(
                    r"project_id: ([0-9a-f-]+)",
                    (Path(tmp) / "docs/memory/manifest.md").read_text(encoding="utf-8"),
                ).group(1)
                local_manifest = Path(state) / "memory-custodian/projects" / project_id / "local/manifest.md"
                local_manifest.write_text("# corrupt\n", encoding="utf-8")
                code, output, _error = self._capture([
                    "read", "--task", "general", "--strict-routing", "--project-root", tmp,
                ])
                self.assertEqual(code, 1)
                self.assertIn("Local overlay status: REVIEW", output)
                self.assertIn("Routing completeness: INCOMPLETE", output)

    def test_check_scans_bound_local_overlay_for_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                project_id = re.search(
                    r"project_id: ([0-9a-f-]+)",
                    (Path(tmp) / "docs/memory/manifest.md").read_text(encoding="utf-8"),
                ).group(1)
                preferences = Path(state) / "memory-custodian/projects" / project_id / "local/preferences.md"
                preferences.write_text("# Local Preferences\n\nsk-abcdefghijklmnopqrstuvwxyz\n", encoding="utf-8")
                code, output, _error = self._capture([
                    "check", "--security", "--project-root", tmp,
                ])
                self.assertEqual(code, 1)
                self.assertIn("local/preferences.md", output)
                self.assertIn("openai-key", output)

    def test_valid_and_invalid_reconciliation_records_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-aaaaaaaa"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {subject_id} — Reconciliation subject\n\n"
                "Status: active\nKind: concept\nEvidence:\n- user-confirmed\n\nAliases:\n- reconciliation subject\n",
                encoding="utf-8",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n"
                f"## MC-DEC-20260801-11111111 — One\n\nStatus: active\nScope: project\nSubject: {subject_id}\nFacet: behavior\nEvidence:\n- user-confirmed\n\nDecision:\nOne.\n\n"
                f"## MC-DEC-20260801-22222222 — Two\n\nStatus: active\nScope: project\nSubject: {subject_id}\nFacet: adoption-policy\nEvidence:\n- user-confirmed\n\nDecision:\nTwo.\n",
                encoding="utf-8",
            )
            valid = (
                "# Reconciliations\n\n## MC-REC-20260801-aaaaaaaa — Independent entries\n\n"
                "Status: active\nResolution: distinct\nEntries:\n"
                "- MC-DEC-20260801-11111111\n- MC-DEC-20260801-22222222\n"
                "Evidence:\n- user-confirmed\n"
            )
            path = memory / "reconciliations.md"
            path.write_text(valid, encoding="utf-8")
            code, output, _error = self._capture(["check", "--conflicts", "--project-root", tmp])
            self.assertEqual(code, 0)
            self.assertIn("Conflict status: CLEAR", output)
            listed = self._capture(["list", "--project-root", tmp])[1]
            self.assertIn("MC-REC-20260801-aaaaaaaa", listed)
            self.assertNotIn("reconciliations.md#unit-", listed)
            path.write_text(valid + valid.replace("aaaaaaaa", "bbbbbbbb"), encoding="utf-8")
            code, output, _error = self._capture(["check", "--conflicts", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("MC-CONFLICT-008 INVALID", output)

    def test_subject_merge_previews_downstream_owner_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            source = "MC-SUBJ-20260801-11111111"
            target = "MC-SUBJ-20260801-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {source} — Source\n\nStatus: active\nKind: concept\nEvidence:\n- user-confirmed\n\nAliases:\n- source\n\n"
                f"## {target} — Target\n\nStatus: active\nKind: concept\nEvidence:\n- user-confirmed\n\nAliases:\n- target\n",
                encoding="utf-8",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n"
                f"## MC-CON-20260801-11111111 — Source owner\n\nStatus: active\nScope: project\nSubject: {source}\nFacet: behavior\nEvidence:\n- user-confirmed\n\nConstraint:\nSource.\n\n"
                f"## MC-CON-20260801-22222222 — Target owner\n\nStatus: active\nScope: project\nSubject: {target}\nFacet: behavior\nEvidence:\n- user-confirmed\n\nConstraint:\nTarget.\n",
                encoding="utf-8",
            )
            before = (memory / "subjects.md").read_text(encoding="utf-8")
            code, output, _error = self._capture([
                "subject", "merge", source, "--into", target, "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("Resulting structural identity", output)
            self.assertIn("Transactional Subject merge apply requires Protocol 0.8.", output)
            self.assertEqual((memory / "subjects.md").read_text(encoding="utf-8"), before)

    def test_unavailable_history_check_is_not_reported_as_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            with patch("memory_custodian.forget.subprocess.run", side_effect=OSError("git unavailable")):
                code, output, _error = self._capture([
                    "forget", "missing-topic", "--mode", "hard", "--history-check", "--project-root", tmp,
                ])
            self.assertEqual(code, 0)
            self.assertIn("History inspection: unavailable", output)
            self.assertIn("is not a PASS", output)


if __name__ == "__main__":
    unittest.main()
