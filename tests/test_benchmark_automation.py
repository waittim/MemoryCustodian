from pathlib import Path
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
    def _record(self, task_id, condition, runtime="test-runtime", repetition="1", status="PASS"):
        task = next(task for task in batch_runner.load_tasks(ROOT) if task["task_id"] == task_id)
        return {
            "result_id": batch_runner.make_result_id(task, condition, runtime, repetition, task["repo"]["commit"]),
            "suite": task["suite"], "task_id": task_id, "task_version": task["task_version"],
            "condition": condition, "runtime": runtime, "repetition_id": repetition,
            "fixture_sha256": task["repo"]["commit"], "model_version": "test-model",
            "tool_policy": "command-adapter", "status": status, "failure_labels": [],
            "evidence_class": "command-adapter",
        }

    def _args(self, directory):
        return ["--tasks", "field-ledger-export-cap", "--conditions", "MEMORYCUSTODIAN",
                "--runtime", "test-runtime", "--model-version", "test-model",
                "--agent-cmd", "echo", "--record-dir", str(directory), "--format", "json"]

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

    def test_resume_includes_saved_records_in_report_without_running_agent(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            record = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN")
            path = directory / (record["result_id"] + ".json")
            original = json.dumps(record)
            path.write_text(original, encoding="utf-8")
            output = io.StringIO()
            with mock.patch.object(batch_runner, "run_single_task", side_effect=AssertionError("must resume")), contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                code = batch_runner.main(self._args(directory) + ["--resume"])
            self.assertEqual(code, 0)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary["by_condition"]["MEMORYCUSTODIAN"]["pass"], 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_resume_does_not_match_another_runtime_or_repetition_prefix(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            old = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN", runtime="another-runtime", repetition="10")
            (directory / (old["result_id"] + ".json")).write_text(json.dumps(old), encoding="utf-8")
            current = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN")
            with mock.patch.object(batch_runner, "run_single_task", return_value=current) as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch_runner.main(self._args(directory) + ["--resume"]), 0)
            run.assert_called_once()

    def test_resume_rejects_model_mismatch_before_launching(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            record = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN")
            record["model_version"] = "different-model"
            (directory / (record["result_id"] + ".json")).write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.object(batch_runner, "run_single_task") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch_runner.main(self._args(directory) + ["--resume"]), 1)
            run.assert_not_called()

    def test_resume_rejects_command_evidence_presented_as_native_live(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            record = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN", runtime="codex")
            record["tool_policy"] = batch_runner.CODEX_TOOL_POLICY
            (directory / (record["result_id"] + ".json")).write_text(json.dumps(record), encoding="utf-8")
            args = ["--tasks", "field-ledger-export-cap", "--conditions", "MEMORYCUSTODIAN",
                    "--mode", "live", "--runtime", "codex", "--model-version", "test-model",
                    "--codex-executable", "/usr/bin/codex", "--record-dir", name, "--resume"]
            with mock.patch.object(batch_runner, "run_single_task") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch_runner.main(args), 1)
            run.assert_not_called()

    def test_existing_result_requires_resume_before_launching(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            record = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN")
            (directory / (record["result_id"] + ".json")).write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.object(batch_runner, "run_single_task") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch_runner.main(self._args(directory)), 1)
            run.assert_not_called()

    def test_blockers_are_excluded_from_paired_failures_and_exit_nonzero(self):
        task_ids = ["task-1", "task-2"]
        conditions = ["EQUIVALENT_MANUAL_DOCS", "MEMORYCUSTODIAN"]
        records = [
            {"task_id": "task-1", "condition": conditions[0], "status": "BLOCKER"},
            {"task_id": "task-1", "condition": conditions[1], "status": "PASS"},
            {"task_id": "task-2", "condition": conditions[0], "status": "FAIL"},
            {"task_id": "task-2", "condition": conditions[1], "status": "PASS"},
        ]
        summary = aggregate_results(task_ids, conditions, records)
        self.assertEqual(summary["paired"]["total_pairs"], 1)
        self.assertEqual(summary["paired"]["incomplete_pairs"], 1)
        self.assertEqual(summary["paired"]["mc_only_pass"], 1)
        with tempfile.TemporaryDirectory() as name:
            blocker = self._record("field-ledger-export-cap", "MEMORYCUSTODIAN", status="BLOCKER")
            with mock.patch.object(batch_runner, "run_single_task", return_value=blocker), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch_runner.main(self._args(name)), 2)

    def test_duplicate_cells_and_out_of_matrix_records_are_rejected(self):
        record = {"task_id": "task-1", "condition": "NO_MEMORY", "status": "PASS"}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            aggregate_results(["task-1"], ["NO_MEMORY"], [record, record])
        with self.assertRaisesRegex(ValueError, "outside"):
            aggregate_results(["another-task"], ["NO_MEMORY"], [record])

    def test_paired_uncertainty_is_reproducible_and_descriptive(self):
        task_ids = ["task-1", "task-2", "task-3"]
        conditions = ["EQUIVALENT_MANUAL_DOCS", "MEMORYCUSTODIAN"]
        records = []
        for task_id, outcomes in zip(task_ids, [("FAIL", "PASS"), ("PASS", "FAIL"), ("PASS", "PASS")]):
            for condition, status in zip(conditions, outcomes):
                records.append({"task_id": task_id, "condition": condition, "status": status})
        first = aggregate_results(task_ids, conditions, records)
        second = aggregate_results(task_ids, conditions, records)
        self.assertEqual(first["paired"], second["paired"])
        self.assertEqual(first["paired"]["success_rate_difference"], 0)
        low, high = first["paired"]["bootstrap_95_interval"]
        self.assertLess(low, 0)
        self.assertGreater(high, 0)
        report = format_markdown_report(first, task_ids, conditions, "test", "test")
        self.assertIn("pilot-development", report)
        self.assertIn("one repetition", report)

    def test_balanced_order_rotates_conditions_and_dry_run_does_not_write(self):
        tasks = ["task-1", "task-2", "task-3", "task-4"]
        conditions = list(batch_runner.CONDITIONS)
        plan = batch_runner.execution_plan(tasks, conditions, "balanced")
        self.assertEqual([condition for _, condition in plan[::4]], conditions)
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "not-created"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch_runner.main(self._args(directory) + ["--dry-run"]), 0)
            self.assertFalse(directory.exists())

    def test_live_options_propagate_without_agent_command(self):
        response = mock.Mock(returncode=0, stdout='[{"status":"PASS"}]', stderr="")
        with mock.patch.object(batch_runner.subprocess, "run", return_value=response) as run:
            batch_runner.run_single_task(ROOT, "task-1", "NO_MEMORY", "codex", None, "1", 120, None,
                                         "model-1", "policy", "live", "/usr/bin/codex")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--mode") + 1], "live")
        self.assertEqual(command[command.index("--codex-executable") + 1], "/usr/bin/codex")
        self.assertNotIn("--agent-cmd", command)


if __name__ == "__main__":
    unittest.main()
