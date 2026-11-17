import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.graders.mechanical import grade_script, run_visible_tests
from benchmarks.runners.harness import command_for, load_tasks, prepare_checkout


REVISION = ROOT / "benchmarks/task-revisions/route-notes-token-estimate/v2"
SPEC = importlib.util.spec_from_file_location("revised_token_estimate_cases", REVISION / "cases.py")
CASES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CASES)
LIBRARY = ROOT / "benchmarks/oracles/_lib"


class RevisedTokenEstimateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = next(task for task in load_tasks(ROOT) if task["task_id"] == "route-notes-token-estimate")
        cls.cases = CASES.build_cases(ROOT)

    def prepare(self, checkout, case):
        prepare_checkout(ROOT, self.task, "MEMORYCUSTODIAN", checkout)
        for relative, source in case["files"].items():
            (checkout / relative).write_text(source, encoding="utf-8")

    def test_fixed_cases_are_safe_complete_deterministic_sources(self):
        self.assertEqual(self.cases, CASES.build_cases(ROOT))
        names = [case["name"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(sum(case["expected_status"] == "PASS" for case in self.cases), 4)
        for case in self.cases:
            with self.subTest(case=case["name"]):
                self.assertRegex(case["name"], re.compile(r"^[a-z0-9-]+$"))
                self.assertEqual(set(case), {"name", "expected_status", "expected_labels", "description", "files"})
                self.assertEqual(set(case["files"]), {"router.py"})
                compile(case["files"]["router.py"], "router.py", "exec")

    def test_v2_accepts_equivalent_implementations_and_rejects_wrong_counts(self):
        for case in self.cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as directory:
                checkout = Path(directory) / "checkout"
                self.prepare(checkout, case)
                result = grade_script(REVISION / "check.py", checkout, LIBRARY)
                self.assertEqual(result["status"], case["expected_status"], result)
                self.assertEqual(result["failure_labels"], case["expected_labels"], result)
                if case["expected_status"] == "PASS":
                    self.assertEqual(run_visible_tests(checkout, command_for(self.task)), "PASS")

    def test_reference_passes_both_oracle_revisions(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            old = grade_script(ROOT / self.task["success_oracle"]["script"], checkout, LIBRARY)
            new = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(old["status"], "PASS")
        self.assertEqual(new["status"], "PASS")

    def test_constant_three_reproduces_old_false_acceptance(self):
        case = next(case for case in self.cases if case["name"] == "constant-three")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            old = grade_script(ROOT / self.task["success_oracle"]["script"], checkout, LIBRARY)
            new = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(old["status"], "PASS")
        self.assertEqual(new["status"], "FAIL")
        self.assertEqual(new["failure_labels"], ["MEMORY_OMISSION"])


if __name__ == "__main__":
    unittest.main()
