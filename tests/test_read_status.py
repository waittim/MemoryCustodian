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

    def test_status_reports_initialized_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                code = main(["status", "--project-root", tmp])
            self.assertEqual(code, 0)
            text = out.getvalue()
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


if __name__ == "__main__":
    unittest.main()
