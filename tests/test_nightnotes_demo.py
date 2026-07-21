import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "nightnotes-video-demo"


class NightNotesDemoTests(unittest.TestCase):
    def run_memory_custodian(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "memory_custodian.main", *args],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / "cli"),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_demo_context_and_compaction_story_do_not_drift(self):
        check = self.run_memory_custodian("check", "--project-root", str(DEMO))
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("MemoryCustodian check: OK", check.stdout)

        planning = self.run_memory_custodian(
            "read", "--project-root", str(DEMO), "--task", "planning"
        )
        self.assertEqual(planning.returncode, 0, planning.stderr)
        for expected in (
            "human-readable local JSON",
            "without network access",
            "Python standard library",
            "Tombstone: SQLite for session persistence",
        ):
            self.assertIn(expected, planning.stdout)
        self.assertNotIn("Consider encrypting exported notes", planning.stdout)
        self.assertNotIn("## inbox.md", planning.stdout)

        compact = self.run_memory_custodian(
            "compact", "--project-root", str(DEMO)
        )
        self.assertEqual(compact.returncode, 0, compact.stderr)
        self.assertIn("Candidates requiring Agent review: 1", compact.stdout)
        self.assertIn("Consider encrypting exported notes", compact.stdout)
        self.assertIn("No semantic destinations are inferred", compact.stdout)

    def test_demo_acceptance_test_fails_only_for_missing_persistence(self):
        acceptance = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=DEMO,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        output = acceptance.stdout + acceptance.stderr
        self.assertNotEqual(acceptance.returncode, 0, output)
        self.assertIn("Notes must survive across separate store instances.", output)
        self.assertIn("FAILED (failures=1)", output)
        self.assertNotIn("ImportError", output)


if __name__ == "__main__":
    unittest.main()
