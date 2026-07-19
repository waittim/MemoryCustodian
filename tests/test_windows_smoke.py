from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from memory_custodian.main import main


class WindowsCliSmokeTests(unittest.TestCase):
    def test_init_read_add_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nCross-platform smoke test.\n",
                encoding="utf-8",
            )
            self.assertEqual(
                main(["add", "Work offline.", "--type", "constraint", "--project-root", tmp]),
                0,
            )
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(["read", "--task", "implementation", "--names-only", "--project-root", tmp]),
                    0,
                )
                self.assertEqual(main(["check", "--project-root", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
