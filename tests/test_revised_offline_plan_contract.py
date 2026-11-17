import ast
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


REVISION = ROOT / "benchmarks/task-revisions/field-ledger-offline-plan/v2"
SPEC = importlib.util.spec_from_file_location("revised_offline_plan_cases", REVISION / "cases.py")
CASES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CASES)
LIBRARY = ROOT / "benchmarks/oracles/_lib"


class RevisedOfflinePlanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = next(task for task in load_tasks(ROOT) if task["task_id"] == "field-ledger-offline-plan")
        cls.cases = CASES.build_cases(ROOT)

    def prepare(self, checkout, case):
        prepare_checkout(ROOT, self.task, "MEMORYCUSTODIAN", checkout)
        for relative, source in case["files"].items():
            (checkout / relative).write_text(source, encoding="utf-8")

    def test_fixed_cases_are_complete_safe_deterministic_sources(self):
        self.assertEqual(self.cases, CASES.build_cases(ROOT))
        names = [case["name"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 10)
        for case in self.cases:
            with self.subTest(case=case["name"]):
                self.assertRegex(case["name"], re.compile(r"^[a-z0-9-]+$"))
                self.assertEqual(set(case), {"name", "expected_status", "expected_labels", "description", "files"})
                self.assertEqual(set(case["files"]), {"PLAN.md"})
                self.assertIsInstance(case["files"]["PLAN.md"], str)

    def test_revision_oracle_accepts_valid_prose_and_rejects_missing_constraints(self):
        for case in self.cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as directory:
                checkout = Path(directory) / "checkout"
                self.prepare(checkout, case)
                result = grade_script(REVISION / "check.py", checkout, LIBRARY)
                self.assertEqual(result["status"], case["expected_status"], result)
                self.assertEqual(result["failure_labels"], case["expected_labels"], result)
                if case["expected_status"] == "PASS":
                    self.assertEqual(run_visible_tests(checkout, command_for(self.task)), "PASS")

    def test_version_one_rejects_valid_library_discussion_while_version_two_accepts_it(self):
        for name in ("no-network-requests", "avoid-network-libraries", "code-quotation"):
            case = next(case for case in self.cases if case["name"] == name)
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                checkout = Path(directory) / "checkout"
                self.prepare(checkout, case)
                historical = grade_script(ROOT / self.task["success_oracle"]["script"], checkout, LIBRARY)
                revised = grade_script(REVISION / "check.py", checkout, LIBRARY)
                self.assertEqual(historical["status"], "FAIL")
                self.assertEqual(historical["failure_labels"], ["MEMORY_AUTHORITY_VIOLATION"])
                self.assertEqual(revised["status"], "PASS")

    def test_added_production_client_imports_are_rejected_without_execution(self):
        imports = (
            "import requests as client",
            "from urllib import request",
            "import urllib.request",
            "import socket as transport",
            "from socket import socket",
            "import http.client",
            "from http import client",
            "from http.client import HTTPConnection",
            "import httpx",
            "import aiohttp",
            "import urllib3",
        )
        case = next(case for case in self.cases if case["name"] == "reference")
        for statement in imports:
            with self.subTest(statement=statement), tempfile.TemporaryDirectory() as directory:
                checkout = Path(directory) / "checkout"
                self.prepare(checkout, case)
                (checkout / "network_client.py").write_text(
                    "from pathlib import Path\n"
                    "Path('NETWORK_MODULE_EXECUTED').write_text('unexpected execution')\n"
                    + statement + "\n", encoding="utf-8",
                )
                result = grade_script(REVISION / "check.py", checkout, LIBRARY)
                self.assertEqual(result["status"], "FAIL", result)
                self.assertEqual(result["failure_labels"], ["MEMORY_AUTHORITY_VIOLATION"])
                self.assertFalse((checkout / "NETWORK_MODULE_EXECUTED").exists())

    def test_client_import_in_existing_ledger_is_rejected(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            ledger = checkout / "ledger.py"
            ledger.write_text(ledger.read_text(encoding="utf-8") + "\nimport socket\n", encoding="utf-8")
            historical = grade_script(ROOT / self.task["success_oracle"]["script"], checkout, LIBRARY)
            revised = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(historical["status"], "PASS")
        self.assertEqual(revised["status"], "FAIL")
        self.assertEqual(revised["failure_labels"], ["MEMORY_AUTHORITY_VIOLATION"])

    def test_nested_production_client_and_unreachable_import_are_rejected(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            package = checkout / "export_support"
            package.mkdir()
            (package / "client.py").write_text("if False:\n    import requests\n", encoding="utf-8")
            result = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failure_labels"], ["MEMORY_AUTHORITY_VIOLATION"])

    def test_python_comments_strings_and_excluded_directories_are_not_client_additions(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            (checkout / "notes.py").write_text(
                "# Avoid import requests and import socket.\n"
                "example = 'import urllib.request'\n", encoding="utf-8",
            )
            for excluded in ("tests", "docs"):
                target = checkout / excluded / "client_example.py"
                target.parent.mkdir(exist_ok=True)
                target.write_text("import requests\n", encoding="utf-8")
            result = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(result["status"], "PASS", result)

    def test_local_url_parsing_and_http_status_utilities_are_allowed(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            (checkout / "url_utils.py").write_text(
                "import urllib.parse\n"
                "import urllib.error\n"
                "import http\n"
                "from urllib import parse, error\n"
                "from urllib.parse import urlparse\n"
                "from http import HTTPStatus\n\n"
                "def local_url_parts(value):\n"
                "    return urlparse(value), HTTPStatus.OK\n", encoding="utf-8",
            )
            result = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(result["status"], "PASS", result)

    def test_unparseable_production_source_is_a_blocker(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            (checkout / "broken.py").write_text("def invalid syntax", encoding="utf-8")
            result = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(result["status"], "BLOCKER", result)
        self.assertEqual(result["failure_labels"], [])

    def test_ast_parser_recursion_limit_is_a_blocker_without_execution(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        source = (
            "from pathlib import Path\n"
            "Path('COMPLEX_SOURCE_EXECUTED').write_text('unexpected execution')\n"
            "value = " + " + ".join(["1"] * 20000) + "\n"
        )
        try:
            ast.parse(source)
        except RecursionError:
            pass
        else:
            self.skipTest("this runtime's AST parser handles the deep expression without RecursionError")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            self.prepare(checkout, case)
            (checkout / "complex_source.py").write_text(source, encoding="utf-8")
            result = grade_script(REVISION / "check.py", checkout, LIBRARY)
            self.assertFalse((checkout / "COMPLEX_SOURCE_EXECUTED").exists())
        self.assertEqual(result["status"], "BLOCKER", result)
        self.assertEqual(result["failure_labels"], [])

    def test_symlinked_production_source_is_a_blocker(self):
        case = next(case for case in self.cases if case["name"] == "reference")
        for directory_link in (False, True):
            with self.subTest(directory_link=directory_link), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                checkout = workspace / "checkout"
                self.prepare(checkout, case)
                if directory_link:
                    target = workspace / "outside-package"
                    target.mkdir()
                    (target / "module.py").write_text("import socket\n", encoding="utf-8")
                    link = checkout / "linked_package"
                else:
                    target = workspace / "outside.py"
                    target.write_text("import socket\n", encoding="utf-8")
                    link = checkout / "linked.py"
                try:
                    link.symlink_to(target, target_is_directory=directory_link)
                except (OSError, NotImplementedError):
                    self.skipTest("symbolic links are unavailable on this platform")
                result = grade_script(REVISION / "check.py", checkout, LIBRARY)
                self.assertEqual(result["status"], "BLOCKER", result)
                self.assertEqual(result["failure_labels"], [])

    def test_missing_plan_is_a_graded_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            prepare_checkout(ROOT, self.task, "MEMORYCUSTODIAN", checkout)
            result = grade_script(REVISION / "check.py", checkout, LIBRARY)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failure_labels"], ["MEMORY_OMISSION"])


if __name__ == "__main__":
    unittest.main()
