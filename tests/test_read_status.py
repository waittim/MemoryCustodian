from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.main import main


class ReadStatusTests(unittest.TestCase):
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
                "### Implementation\n"
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
            self.assertEqual(code, 0)
            text = out.getvalue()
            self.assertIn("CLI version: 0.6.0", text)
            self.assertIn("Protocol version: 0.4 (current)", text)
            self.assertIn("brief.md: OK", text)
            self.assertIn("inbox.md: OK", text)
            self.assertIn("preferences.md: not enabled", text)

    def test_check_reports_initialized_memory_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 0)
            self.assertIn("MemoryCustodian check: OK", out.getvalue())

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
            self.assertIn("- protocol_version: 0.4", migrated)
            self.assertIn("- initialized_with: unknown", migrated)
            self.assertIn("## Optional module index", migrated)

            out = StringIO()
            with redirect_stdout(out):
                code = main(["check", "--project-root", tmp])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
