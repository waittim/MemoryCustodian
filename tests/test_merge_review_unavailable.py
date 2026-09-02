"""Regression coverage for fail-closed merge-review availability."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest

from memory_custodian.main import main
from memory_custodian.merge_review import merge_review


def capture(argv: list[str]) -> tuple[int, str, str]:
    output, error = StringIO(), StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        code = main(argv)
    return code, output.getvalue(), error.getvalue()


def git(root: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def initialize_git_project(root: str) -> Path:
    with redirect_stdout(StringIO()):
        assert main(["init", "--project-root", root]) == 0
    memory = Path(root) / "docs" / "memory"
    git(root, "init", "-q")
    git(root, "config", "user.name", "MemoryCustodian Tests")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return memory


class MergeReviewAvailabilityTests(unittest.TestCase):
    def test_missing_merge_base_is_blocking_in_api_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            result = merge_review(Path(tmp), memory, "does-not-exist")
            self.assertTrue(result.blocking)
            self.assertIn("Merge review unavailable:", result.text)
            self.assertIn("Conflict-free status was not established.", result.text)

            code, output, error = capture([
                "check", "--conflicts", "--merge-base", "does-not-exist",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("Conflict status: CLEAR", output)
            self.assertIn("Merge review unavailable:", output)
            self.assertIn("Conflict-free status was not established.", output)

    def test_unclosed_subject_fence_in_target_is_a_structured_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            head_ref = git(tmp, "branch", "--show-current")
            git(tmp, "checkout", "-qb", "malformed-subjects")
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n```text\nunterminated\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "malformed target subjects")
            git(tmp, "checkout", "-q", head_ref)

            result = merge_review(Path(tmp), memory, "malformed-subjects")
            self.assertTrue(result.blocking)
            self.assertIn("Merge review status: CONFLICT", result.text)
            self.assertIn("MC-MERGE-006", result.text)
            self.assertIn("Unclosed fenced code block", result.text)
            self.assertNotIn("Merge review unavailable:", result.text)

            code, output, error = capture([
                "check", "--conflicts", "--merge-base", "malformed-subjects",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("Merge review status: CONFLICT", output)
            self.assertIn("MC-MERGE-006", output)
            self.assertIn("Unclosed fenced code block", output)

    def test_unclosed_reconciliation_fence_in_target_is_a_structured_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            head_ref = git(tmp, "branch", "--show-current")
            git(tmp, "checkout", "-qb", "malformed-reconciliations")
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n```text\nunterminated\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "malformed target reconciliations")
            git(tmp, "checkout", "-q", head_ref)

            result = merge_review(Path(tmp), memory, "malformed-reconciliations")
            self.assertTrue(result.blocking)
            self.assertIn("Merge review status: CONFLICT", result.text)
            self.assertIn("MC-MERGE-006", result.text)
            self.assertIn("Unclosed fenced code block", result.text)
            self.assertNotIn("Merge review unavailable:", result.text)

            code, output, error = capture([
                "check", "--conflicts", "--merge-base", "malformed-reconciliations",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("Merge review status: CONFLICT", output)
            self.assertIn("MC-MERGE-006", output)
            self.assertIn("Unclosed fenced code block", output)


if __name__ == "__main__":
    unittest.main()
