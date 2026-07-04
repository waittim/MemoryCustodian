from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillEvalTests(unittest.TestCase):
    def test_skill_eval_contracts_are_current(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-skill-evals.py")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MemoryCustodian skill eval check: OK", result.stdout)
        self.assertIn("Scenarios: 5", result.stdout)


if __name__ == "__main__":
    unittest.main()
