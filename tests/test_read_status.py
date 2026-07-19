from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.main import main


class ReadStatusTests(unittest.TestCase):
    def test_read_rejects_invalid_explicit_profile_and_area_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            for option, noun in (("--profile", "profile"), ("--area", "area")):
                with self.subTest(option=option):
                    out = StringIO()
                    err = StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        code = main(["read", "--project-root", tmp, option, "../backend"])
                    self.assertEqual(code, 2)
                    self.assertEqual(out.getvalue(), "")
                    self.assertIn(f"Error: Invalid {noun} name: ../backend", err.getvalue())

    def test_read_architecture_loads_task_specific_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["read", "--project-root", tmp, "--task", "architecture", "--names-only"]), 0)
            text = out.getvalue()
            self.assertIn("- brief.md", text)
            self.assertIn("- decisions.md", text)
            self.assertIn("- constraints.md", text)
            self.assertIn("- do-not-use.md", text)
            self.assertNotIn("- inbox.md", text)

    def test_read_implementation_skips_missing_optional_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["read", "--project-root", tmp, "--task", "implementation", "--names-only"]), 0)
            text = out.getvalue()
            self.assertIn("- brief.md", text)
            self.assertIn("- decisions.md", text)
            self.assertIn("- constraints.md", text)
            self.assertIn("- do-not-use.md", text)
            self.assertIn("Skipped optional:", text)
            self.assertIn("- preferences.md", text)

    def test_read_uses_project_manifest_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            manifest.write_text(
                "# Memory Manifest\n\n"
                "## Always load\n"
                "- brief.md\n\n"
                "## Load by task\n\n"
                "### Implementation / execution / debugging\n"
                "Load:\n"
                "- constraints.md\n"
                "Load if present:\n"
                "- preferences.md\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["read", "--project-root", tmp, "--task", "implementation", "--names-only"]), 0)
            text = out.getvalue()
            self.assertIn("- brief.md", text)
            self.assertIn("- constraints.md", text)
            self.assertNotIn("- do-not-use.md", text)

    def test_status_reports_initialized_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                code = main(["status", "--project-root", tmp])
            self.assertEqual(code, 1)
            text = out.getvalue()
            self.assertIn("CLI version: 0.9.0", text)
            self.assertIn("Protocol version: 0.5 (current)", text)
            self.assertIn("brief.md: NEEDS CURATION", text)
            self.assertIn("inbox.md: OK", text)
            self.assertIn("preferences.md: not enabled", text)

    def test_check_reports_initialized_memory_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            (Path(tmp) / "docs" / "memory" / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nA real test project.\n\nCurrent direction:\nValidate memory.\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 0)
            self.assertIn("MemoryCustodian check: OK", out.getvalue())

    def test_check_rejects_uncurated_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("generated scaffold still needs real project", out.getvalue())

    def test_check_suggests_target_compaction_for_over_budget_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            repeated = "\n".join("- Must keep duplicate constraint." for _ in range(120))
            (memory / "constraints.md").write_text("# Constraints\n\n" + repeated + "\n", encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("memory-custodian compact --target constraints.md", out.getvalue())

    def test_check_reports_unindexed_optional_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            area = Path(tmp) / "docs" / "memory" / "areas"
            area.mkdir()
            (area / "frontend.md").write_text("# Area: Frontend\n", encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("areas/frontend.md exists but is missing from optional module index", out.getvalue())

    def test_check_reports_missing_protocol_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            manifest.write_text(
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
                "- profiles/\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("missing MemoryCustodian Protocol metadata", out.getvalue())

    def test_migrate_adds_protocol_metadata_and_optional_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            manifest.write_text(
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
                "- profiles/\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["migrate", "--project-root", tmp]), 0)
            self.assertIn("Dry run only", out.getvalue())
            self.assertNotIn("MemoryCustodian Protocol", manifest.read_text(encoding="utf-8"))

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["migrate", "--project-root", tmp, "--apply"]), 0)
            migrated = manifest.read_text(encoding="utf-8")
            self.assertIn("## MemoryCustodian Protocol", migrated)
            self.assertIn("- protocol_version: 0.5", migrated)
            self.assertIn("- initialized_with: unknown", migrated)
            self.assertIn("## Optional module index", migrated)

            (Path(tmp) / "docs" / "memory" / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nMigration test project.\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("route: expected one canonical heading", out.getvalue())

    def test_migrate_updates_generated_implementation_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            legacy = manifest.read_text(encoding="utf-8").replace(
                "### Implementation / execution / debugging\nLoad:\n- decisions.md\n- constraints.md",
                "### Implementation / execution / debugging\nLoad:\n- constraints.md",
            ).replace("- protocol_version: 0.5", "- protocol_version: 0.4")
            manifest.write_text(legacy, encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["migrate", "--project-root", tmp, "--apply"]), 0)
            migrated = manifest.read_text(encoding="utf-8")
            implementation = migrated.split("### Implementation / execution / debugging", 1)[1].split("###", 1)[0]
            self.assertIn("- decisions.md", implementation)
            self.assertIn("load decisions.md for implementation", out.getvalue())

    def test_migrate_rejects_newer_protocol_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            manifest = memory / "manifest.md"
            newer = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5", "- protocol_version: 0.6"
            )
            manifest.write_text(newer, encoding="utf-8")

            err = StringIO()
            with redirect_stderr(err):
                code = main(["migrate", "--project-root", tmp, "--apply"])

            self.assertEqual(code, 2)
            self.assertIn("newer than this CLI supports", err.getvalue())
            self.assertEqual(manifest.read_text(encoding="utf-8"), newer)

    def test_migrate_rejects_invalid_protocol_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            invalid = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5", "- protocol_version: future"
            )
            manifest.write_text(invalid, encoding="utf-8")

            err = StringIO()
            with redirect_stderr(err):
                code = main(["migrate", "--project-root", tmp, "--apply"])

            self.assertEqual(code, 2)
            self.assertIn("invalid protocol version", err.getvalue().lower())
            self.assertEqual(manifest.read_text(encoding="utf-8"), invalid)

    def test_check_warns_about_machine_specific_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text("# Project Brief\n\nPurpose:\nPortable project.\n", encoding="utf-8")
            (memory / "preferences.md").write_text(
                "# Preferences\n\n- Use /Volumes/Local/Xcode.app for builds.\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 0)
            self.assertIn("machine-specific absolute path", out.getvalue())

    def test_status_and_check_report_long_decision_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text("# Project Brief\n\nPurpose:\nDecision quality test.\n", encoding="utf-8")
            message = " ".join(f"detail{index}" for index in range(140))
            self.assertEqual(
                main(["add", message, "--type", "decision", "--allow-long", "--project-root", tmp]),
                0,
            )

            status_out = StringIO()
            with redirect_stdout(status_out):
                status_code = main(["status", "--project-root", tmp])
            self.assertEqual(status_code, 1)
            self.assertIn("decisions.md: LONG ENTRIES", status_out.getvalue())

            check_out = StringIO()
            with redirect_stdout(check_out):
                check_code = main(["check", "--project-root", tmp])
            self.assertEqual(check_code, 1)
            self.assertIn("decision", check_out.getvalue())
            self.assertIn("is too long", check_out.getvalue())


if __name__ == "__main__":
    unittest.main()
