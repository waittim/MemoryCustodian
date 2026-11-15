"""Static evidence checks use synthetic records, never launch an agent."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("benchmark_evidence", ROOT / "scripts/check-benchmark-evidence.py")
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


class BenchmarkEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks, cls.inputs = evidence.expected_inputs(ROOT)
        cls.records = []
        sources = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in evidence.SOURCE_PATHS}
        for task in cls.tasks:
            for condition in evidence.CONDITIONS:
                visible = cls.inputs[(task["task_id"], condition)]
                index = len(cls.records)
                cls.records.append({
                    "result_format": "1", "result_id": evidence.make_result_id(task, condition, "codex", evidence.REPETITION, task["repo"]["commit"]),
                    "status": "PASS", "evidence_class": "live-runtime", "suite": "core",
                    "task_id": task["task_id"], "task_version": task["task_version"],
                    "condition": condition, "runtime": "codex", "model_version": evidence.MODEL,
                    "tool_policy": evidence.POLICY, "budget": deepcopy(evidence.BUDGET),
                    "repetition_id": evidence.REPETITION, "package_version": "0.13.0", "protocol_version": "0.8",
                    "git_commit": "a" * 40, "git_dirty": True, "os": "synthetic-test-os",
                    "runner_source_sha256": deepcopy(sources), "prompt_sha256": evidence.digest(task["task_prompt"]),
                    "fixture_sha256": task["repo"]["commit"], "visible_source_sha256": visible, "checkout_id": visible,
                    "failure_labels": [], "memory_label": "MEMORY_NONE",
                    "metrics": {
                        "task_success": True, "hard_constraint_violation": False,
                        "memory_dependent_requirement_satisfied": True, "stale_memory_used": False,
                        "unsupported_memory_used": False, "routing_complete": None,
                        "context_memory_tokens": None, "repeated_file_reads": None,
                        "total_input_tokens": 10, "total_output_tokens": 5, "tool_calls": 0,
                        "wall_clock_seconds": 1.5, "tests_run": True, "final_test_status": "PASS",
                    },
                    "runtime_metadata": {
                        "adapter": "codex-exec-jsonl-v1", "cli_version": "codex-cli synthetic-test",
                        "requested_model": evidence.MODEL, "tool_policy": evidence.POLICY,
                        "completion_events": 1, "exit_code": 0, "raw_trace_retained": False,
                        "prompt_prefix_sha256": evidence.digest(evidence.PREFIX),
                        "effective_prompt_sha256": evidence.digest(evidence.PREFIX + task["task_prompt"]),
                        "thread_id": f"synthetic-test-session-{index}", "event_stream_sha256": f"{index:064x}",
                        "stderr_sha256": "e" * 64, "event_count": 3, "total_input_tokens": 10,
                        "total_output_tokens": 5, "tool_calls": 0, "cached_input_tokens": 2,
                        "action_trace": [{"event": "item.completed", "type": "agent_message", "id": "item-1", "text_sha256": "f" * 64}],
                    },
                })

    def check(self, records, **kwargs):
        return evidence.validate_records(ROOT, records, self.tasks, self.inputs, **kwargs)

    def test_complete_matrix_and_graded_failure_are_valid_without_execution(self):
        records = deepcopy(self.records)
        records[0]["status"] = "FAIL"
        records[0]["failure_labels"] = ["MEMORY_OMISSION"]
        records[0]["memory_label"] = "MEMORY_OMISSION"
        records[0]["metrics"]["task_success"] = False
        records[0]["metrics"]["memory_dependent_requirement_satisfied"] = False
        with mock.patch("subprocess.run", side_effect=AssertionError("no runtime or grader")):
            self.assertEqual(self.check(records), [])

    def test_missing_and_duplicate_cells_are_rejected(self):
        self.assertTrue(any("missing 1" in issue for issue in self.check(self.records[:-1])))
        records = deepcopy(self.records)
        records[-1] = deepcopy(records[0])
        issues = self.check(records)
        self.assertTrue(any("duplicate task/condition" in issue for issue in issues))
        self.assertTrue(any("duplicate result ID" in issue for issue in issues))
        self.assertTrue(any("missing 1" in issue for issue in issues))

    def test_session_reuse_and_fake_native_label_are_rejected(self):
        records = deepcopy(self.records)
        records[1]["runtime_metadata"]["thread_id"] = records[0]["runtime_metadata"]["thread_id"]
        records[0]["evidence_class"] = "command-adapter"
        issues = self.check(records)
        self.assertTrue(any("reused session" in issue for issue in issues))
        self.assertTrue(any("evidence_class" in issue for issue in issues))

    def test_cross_condition_input_hash_and_prompt_tampering_are_rejected(self):
        records = deepcopy(self.records)
        records[0]["visible_source_sha256"] = records[3]["visible_source_sha256"]
        records[0]["prompt_sha256"] = "0" * 64
        issues = self.check(records)
        self.assertTrue(any("visible_source_sha256" in issue for issue in issues))
        self.assertTrue(any("prompt_sha256" in issue for issue in issues))

    def test_incomplete_turn_and_false_pass_are_rejected(self):
        records = deepcopy(self.records)
        records[0]["runtime_metadata"]["completion_events"] = 0
        records[0]["metrics"]["final_test_status"] = "FAIL"
        records[1]["status"] = "BLOCKER"
        records[1]["evidence_class"] = "live-runtime-unavailable"
        issues = self.check(records)
        self.assertTrue(any("completion_events" in issue for issue in issues))
        self.assertTrue(any("recorded oracle/visible-test gate" in issue for issue in issues))
        self.assertTrue(any("incomplete pilot" in issue for issue in issues))

    def test_malformed_metrics_and_runtime_fields_are_rejected(self):
        records = deepcopy(self.records)
        records[0]["metrics"]["total_input_tokens"] = True
        records[0]["metrics"]["wall_clock_seconds"] = float("nan")
        records[0]["metrics"]["routing_complete"] = True
        records[0]["runtime_metadata"]["exit_code"] = False
        records[1]["status"] = []
        records[1]["metrics"]["final_test_status"] = []
        records[1]["runtime_metadata"]["action_trace"][0]["type"] = []
        issues = self.check(records)
        self.assertTrue(any("observed total_input_tokens" in issue for issue in issues))
        self.assertTrue(any("observed duration" in issue for issue in issues))
        self.assertTrue(any("routing_complete" in issue for issue in issues))
        self.assertTrue(any("runtime exit_code" in issue for issue in issues))
        self.assertTrue(any("action event" in issue for issue in issues))

    def test_historical_hashes_must_agree_and_current_source_is_opt_in(self):
        historical = deepcopy(self.records)
        for record in historical:
            record["runner_source_sha256"] = {path: "0" * 64 for path in evidence.SOURCE_PATHS}
        self.assertEqual(self.check(historical), [])
        self.assertTrue(any("current source" in issue for issue in self.check(historical, check_current_source=True)))
        historical[-1]["runner_source_sha256"][evidence.SOURCE_PATHS[0]] = "1" * 64
        self.assertTrue(any("changed within" in issue for issue in self.check(historical)))

    def test_malformed_json_duplicate_fields_and_filename_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "record.json"
            path.write_text('{"result_id":"record","result_id":"record"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON field"):
                evidence.load_records(directory)
            path.write_text('{"result_id":"record","x":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite"):
                evidence.load_records(directory)
            path.write_text('{"result_id":"other"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "filename"):
                evidence.load_records(directory)

    def test_report_reproduction_detects_a_changed_result_row(self):
        with tempfile.TemporaryDirectory() as name:
            report = Path(name) / "RESULTS.md"
            path = ROOT / "scripts/run-batch-benchmark.py"
            spec = importlib.util.spec_from_file_location("batch_evidence_test", path)
            batch = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(batch)
            tasks = [task["task_id"] for task in self.tasks]
            summary = batch.aggregate_results(tasks, list(evidence.CONDITIONS), self.records)
            text = batch.format_markdown_report(summary, tasks, list(evidence.CONDITIONS), "codex", evidence.MODEL)
            report.write_text(text + "\nHistorical pilot appendix.\n", encoding="utf-8")
            self.assertEqual(evidence.check_report(ROOT, report, self.records, self.tasks), [])
            report.write_text(text.replace("18 | 18 | 0 | 0 | 0 |", "18 | 17 | 1 | 0 | 0 |", 1), encoding="utf-8")
            self.assertTrue(evidence.check_report(ROOT, report, self.records, self.tasks))


if __name__ == "__main__":
    unittest.main()
