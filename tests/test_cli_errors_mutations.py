from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from tests.cli_test_support import main
from tests.cli_test_support import _subject_for_add
from memory_custodian.protocol import write_text as actual_write_text


class CliErrorAndMutationTests(unittest.TestCase):
    def test_value_error_is_written_to_stderr_with_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            err = StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["init", "--project-root", tmp, "--memory-dir", "outside"])
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("Error: Memory directory must live under docs/", err.getvalue())

    def test_expected_os_error_is_written_to_stderr_without_traceback(self):
        out = StringIO()
        err = StringIO()
        with patch("memory_custodian.main.status_cmd.run", side_effect=OSError("disk unavailable")):
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["status"])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "I/O error: disk unavailable\n")
        self.assertNotIn("Traceback", err.getvalue())

    def _fail_second_write(self):
        calls = 0

        def side_effect(path: Path, text: str) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second write failure")
            actual_write_text(path, text)

        return side_effect

    def test_add_reports_transaction_failure_before_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            add_args = _subject_for_add(
                [
                    "add",
                    "Backend candidate.",
                    "--type",
                    "area",
                    "--name",
                    "backend",
                    "--project-root",
                    tmp,
                ]
            )
            err = StringIO()
            with patch(
                "memory_custodian.transactions._same_filesystem_replace",
                side_effect=OSError("simulated transaction write failure"),
            ):
                with redirect_stdout(StringIO()), redirect_stderr(err):
                    code = main(add_args)

            self.assertEqual(code, 1)
            self.assertFalse((memory / "areas" / "backend.md").exists())
            self.assertNotIn("`areas/backend.md`", (memory / "manifest.md").read_text(encoding="utf-8"))
            self.assertIn("simulated transaction write failure", err.getvalue())

    def test_enable_reports_transaction_failure_before_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            err = StringIO()
            with patch(
                "memory_custodian.transactions._same_filesystem_replace",
                side_effect=OSError("simulated transaction write failure"),
            ):
                with redirect_stdout(StringIO()), redirect_stderr(err):
                    code = main(["enable", "area/frontend", "--project-root", tmp])

            self.assertEqual(code, 1)
            self.assertFalse((memory / "areas" / "frontend.md").exists())
            self.assertNotIn("`areas/frontend.md`", (memory / "manifest.md").read_text(encoding="utf-8"))
            self.assertIn("simulated transaction write failure", err.getvalue())

    def test_compact_reports_transaction_failure_before_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            inbox = memory / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n## Today\n- Exact duplicate.\n- Exact duplicate.\n- Candidate remains.\n",
                encoding="utf-8",
            )
            err = StringIO()
            before = inbox.read_text(encoding="utf-8")
            with patch(
                "memory_custodian.transactions._same_filesystem_replace",
                side_effect=OSError("simulated transaction write failure"),
            ):
                with redirect_stdout(StringIO()), redirect_stderr(err):
                    code = main(["compact", "--apply", "--project-root", tmp])

            self.assertEqual(code, 1)
            self.assertEqual(inbox.read_text(encoding="utf-8"), before)
            self.assertIn("simulated transaction write failure", err.getvalue())

    def test_target_compaction_preflights_archive_parent_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            entries = []
            for index in range(12):
                words = " ".join(f"word{index}_{number}" for number in range(80))
                entries.append(
                    f"## 2026-01-{index + 1:02d} - Decision marker {index}\n"
                    f"Decision:\nKeep decision marker {index}. {words}\n"
                    f"Reason:\nReason marker {index}."
                )
            decisions = memory / "decisions.md"
            decisions.write_text(
                "# Decisions\n\nEntries are newest first.\n\n" + "\n\n".join(entries) + "\n",
                encoding="utf-8",
            )
            original = decisions.read_text(encoding="utf-8")
            archive = memory / "archive"
            archive.write_text("This path deliberately blocks the archive directory.\n", encoding="utf-8")

            out = StringIO()
            err = StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(
                    [
                        "compact",
                        "--project-root",
                        tmp,
                        "--target",
                        "decisions.md",
                        "--apply",
                        "--archive-oldest",
                    ]
                )

            self.assertEqual(code, 2)
            self.assertIn("archive", err.getvalue())
            self.assertIn("non-directory parent", err.getvalue().lower())
            self.assertNotIn("Partial completion", err.getvalue())
            self.assertEqual(decisions.read_text(encoding="utf-8"), original)
            self.assertEqual(
                archive.read_text(encoding="utf-8"),
                "This path deliberately blocks the archive directory.\n",
            )


if __name__ == "__main__":
    unittest.main()
