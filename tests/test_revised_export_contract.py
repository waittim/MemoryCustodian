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


REVISION = ROOT / "benchmarks/task-revisions/field-ledger-split-export/v2"
SPEC = importlib.util.spec_from_file_location("revised_export_cases", REVISION / "cases.py")
CASES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CASES)
LIBRARY = ROOT / "benchmarks/oracles/_lib"


class RevisedExportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = next(task for task in load_tasks(ROOT) if task["task_id"] == "field-ledger-split-export")
        cls.cases = CASES.build_cases(ROOT)

    def prepare(self, checkout, case):
        prepare_checkout(ROOT, self.task, "MEMORYCUSTODIAN", checkout)
        for relative, source in case["files"].items():
            (checkout / relative).write_text(source, encoding="utf-8")

    def test_fixed_cases_are_complete_safe_deterministic_sources(self):
        self.assertEqual(self.cases, CASES.build_cases(ROOT))
        names = [case["name"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 13)
        for case in self.cases:
            with self.subTest(case=case["name"]):
                self.assertRegex(case["name"], re.compile(r"^[a-z0-9-]+$"))
                self.assertEqual(set(case), {"name", "expected_status", "expected_labels", "description", "files"})
                self.assertEqual(set(case["files"]), {"ledger.py", "export.py"})
                for path, source in case["files"].items():
                    self.assertIsInstance(source, str)
                    compile(source, path, "exec")

    def test_revision_oracle_accepts_valid_variants_and_rejects_invalid_controls(self):
        for case in self.cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as directory:
                checkout = Path(directory) / "checkout"
                self.prepare(checkout, case)
                result = grade_script(REVISION / "check.py", checkout, LIBRARY)
                self.assertEqual(result["status"], case["expected_status"], result)
                self.assertEqual(result["failure_labels"], case["expected_labels"], result)
                if case["expected_status"] == "PASS":
                    self.assertEqual(run_visible_tests(checkout, command_for(self.task)), "PASS")

    def test_version_one_false_negative_on_valid_renamed_helper_is_preserved(self):
        case = next(case for case in self.cases if case["name"] == "renamed-helper")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            historical = grade_script(ROOT / self.task["success_oracle"]["script"], checkout, LIBRARY)
            revised = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(historical["status"], "FAIL")
        self.assertEqual(historical["failure_labels"], ["MEMORY_OMISSION"])
        self.assertEqual(revised["status"], "PASS")

    def test_version_one_false_positive_on_comment_is_preserved(self):
        case = next(case for case in self.cases if case["name"] == "comment-masquerade")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            historical = grade_script(ROOT / self.task["success_oracle"]["script"], checkout, LIBRARY)
            revised = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(historical["status"], "PASS")
        self.assertEqual(revised["status"], "FAIL")
        self.assertEqual(revised["failure_labels"], ["MEMORY_OMISSION"])


if __name__ == "__main__":
    unittest.main()
