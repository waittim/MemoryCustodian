from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _import_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


headless_adapter = _import_script("headless_agent_adapter", ROOT / "scripts" / "headless-agent-adapter.py")
apply_edits_from_text = headless_adapter.apply_edits_from_text
run_mock = headless_adapter.run_mock

batch_runner = _import_script("run_batch_benchmark", ROOT / "scripts" / "run-batch-benchmark.py")
aggregate_results = batch_runner.aggregate_results
format_markdown_report = batch_runner.format_markdown_report


class HeadlessAgentAdapterTests(unittest.TestCase):
    def test_apply_edits_from_text_explicit(self):
        with tempfile.TemporaryDirectory() as name:
            checkout = Path(name)
            response = (
                "Here is the change:\n\n"
                "*** FILE: src/hello.py ***\n"
                "def hello():\n"
                "    return 'world'\n"
                "*** END FILE ***\n"
            )
            applied = apply_edits_from_text(checkout, response)
            self.assertEqual(applied, ["src/hello.py"])
            self.assertEqual((checkout / "src/hello.py").read_text(encoding="utf-8"), "def hello():\n    return 'world'\n")

    def test_apply_edits_from_text_markdown_fence(self):
        with tempfile.TemporaryDirectory() as name:
            checkout = Path(name)
            response = (
                "File: `app/main.py`\n"
                "```python\n"
                "print('test')\n"
                "```\n"
            )
            applied = apply_edits_from_text(checkout, response)
            self.assertEqual(applied, ["app/main.py"])
            self.assertEqual((checkout / "app/main.py").read_text(encoding="utf-8"), "print('test')\n")

    def test_mock_heuristic_respects_memory_presence(self):
        with tempfile.TemporaryDirectory() as name:
            checkout = Path(name)
            # Case 1: No memory -> applies negative or leaves starter
            run_mock(checkout, ROOT, "field-ledger-export-cap", "heuristic")
            self.assertTrue((checkout / "ledger.py").exists())
            text_without_memory = (checkout / "ledger.py").read_text(encoding="utf-8")
            self.assertIn("EXPORT_CAP = 1000", text_without_memory)

            # Case 2: With memory -> applies reference (EXPORT_CAP = 500)
            (checkout / "docs" / "memory").mkdir(parents=True, exist_ok=True)
            run_mock(checkout, ROOT, "field-ledger-export-cap", "heuristic")
            text_with_memory = (checkout / "ledger.py").read_text(encoding="utf-8")
            self.assertIn("EXPORT_CAP = 500", text_with_memory)


class BatchBenchmarkRunnerTests(unittest.TestCase):
    def test_dry_run_batch_runner(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run-batch-benchmark.py"),
                "--tasks",
                "field-ledger-export-cap",
                "--agent-cmd",
                "echo",
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Planned execution matrix:", proc.stdout)
        self.assertIn("field-ledger-export-cap", proc.stdout)

    def test_aggregate_results_and_markdown_formatting(self):
        task_ids = ["task-1"]
        conditions = ["NO_MEMORY", "PLATFORM_FILE_ONLY", "EQUIVALENT_MANUAL_DOCS", "MEMORYCUSTODIAN"]
        records = [
            {"task_id": "task-1", "condition": "NO_MEMORY", "status": "FAIL", "failure_labels": ["MEMORY_OMISSION"]},
            {"task_id": "task-1", "condition": "PLATFORM_FILE_ONLY", "status": "FAIL", "failure_labels": ["MEMORY_OMISSION"]},
            {"task_id": "task-1", "condition": "EQUIVALENT_MANUAL_DOCS", "status": "PASS", "failure_labels": []},
            {"task_id": "task-1", "condition": "MEMORYCUSTODIAN", "status": "PASS", "failure_labels": []},
        ]
        summary = aggregate_results(task_ids, conditions, records)
        self.assertEqual(summary["by_condition"]["MEMORYCUSTODIAN"]["pass"], 1)
        self.assertEqual(summary["by_condition"]["NO_MEMORY"]["fail"], 1)
        self.assertEqual(summary["paired"]["both_pass"], 1)

        md = format_markdown_report(summary, task_ids, conditions, "test-runtime", "v1")
        self.assertIn("# Memory Benchmark Evaluation Report", md)
        self.assertIn("`MEMORYCUSTODIAN`", md)
        self.assertIn("100.0%", md)


if __name__ == "__main__":
    unittest.main()
