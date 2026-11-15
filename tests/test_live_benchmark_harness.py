from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners import harness


class LiveBenchmarkHarnessTests(unittest.TestCase):
    def setUp(self):
        self.task = next(task for task in harness.load_tasks(ROOT)
                         if task["task_id"] == "field-ledger-export-cap")

    def _grade(self, **overrides):
        args = dict(condition="MEMORYCUSTODIAN", runtime="codex", repetition="test",
                    grade="starter", evidence_class="live-runtime", tool_policy="test-policy",
                    model_version="test-model", command=None, timeout=10)
        args.update(overrides)
        return harness.grade_mode(ROOT, [self.task], **args)[0]

    def _runtime(self, runner):
        module = types.ModuleType("benchmarks.runners.codex_runtime")
        module.run_codex = runner
        module.TOOL_POLICY = "test-native-policy"
        return mock.patch.dict(sys.modules, {"benchmarks.runners.codex_runtime": module})

    def test_native_adapter_receives_only_isolated_checkout_and_prompt(self):
        observed = {}

        def run(checkout, prompt, **kwargs):
            self.assertNotIn(ROOT, checkout.parents)
            self.assertEqual(checkout.name, "checkout")
            self.assertFalse((checkout / "benchmarks").exists())
            self.assertEqual(prompt, self.task["task_prompt"])
            self.assertEqual(kwargs, dict(executable="codex-test", model="test-model", timeout=10))
            observed["before"] = harness.tree_hash(checkout)
            shutil.copyfile(ROOT / self.task["offline_expectations"]["reference_dir"] / "ledger.py",
                            checkout / "ledger.py")
            observed["after"] = harness.tree_hash(checkout)
            return {"status": "completed", "detail": "", "metrics": {
                "total_input_tokens": 123, "total_output_tokens": 45,
                "tool_calls": 2, "task_success": False,
            }, "runtime_metadata": {"cli_version": "test"}}

        with self._runtime(run):
            record = self._grade(codex_executable="codex-test")
        self.assertEqual(record["status"], "PASS")
        self.assertEqual(record["evidence_class"], "live-runtime")
        self.assertEqual(record["visible_source_sha256"], observed["before"])
        self.assertNotEqual(observed["before"], observed["after"])
        self.assertTrue(record["metrics"]["task_success"])
        self.assertEqual(record["metrics"]["total_input_tokens"], 123)
        self.assertEqual(record["metrics"]["total_output_tokens"], 45)
        self.assertEqual(record["runtime_metadata"], {"cli_version": "test"})
        self.assertEqual(record["budget"]["time_seconds"], 10)
        self.assertIsInstance(record["git_dirty"], bool)
        self.assertEqual(record["runner_source_sha256"], {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in (
                "benchmarks/graders/mechanical.py",
                "benchmarks/runners/codex_runtime.py",
                "benchmarks/runners/harness.py",
                "scripts/run-batch-benchmark.py",
            )
        })

    def test_native_blocker_preserves_configuration_without_claiming_outcome(self):
        def run(checkout, prompt, **kwargs):
            return {"status": "blocked", "detail": "runtime unavailable",
                    "metrics": {"total_input_tokens": 999},
                    "runtime_metadata": {"unverified": True}}

        with self._runtime(run):
            record = self._grade(codex_executable="codex-test")
        self.assertEqual(record["status"], "BLOCKER")
        self.assertEqual(record["evidence_class"], "live-runtime-unavailable")
        self.assertEqual(record["model_version"], "test-model")
        self.assertEqual(record["tool_policy"], "test-policy")
        self.assertEqual(record["budget"]["time_seconds"], 10)
        self.assertIsNone(record["metrics"]["task_success"])
        self.assertIsNone(record["metrics"]["memory_dependent_requirement_satisfied"])
        self.assertIsNone(record["metrics"]["total_input_tokens"])
        self.assertNotIn("runtime_metadata", record)
        self.assertGreaterEqual(record["metrics"]["wall_clock_seconds"], 0)

    def test_passing_hidden_oracle_cannot_hide_visible_test_failure(self):
        graded = {"status": "PASS", "failure_labels": [], "memory_label": "MEMORY_NONE",
                  "detail": "", "metrics": {"task_success": True}}
        with mock.patch.object(harness, "grade_checkout", return_value=graded), \
                mock.patch.object(harness, "run_visible_tests", return_value="FAIL"):
            record = self._grade(evidence_class="offline-fixture")
        self.assertEqual(record["status"], "FAIL")
        self.assertFalse(record["metrics"]["task_success"])
        self.assertEqual(record["metrics"]["final_test_status"], "FAIL")
        self.assertIn("visible tests: FAIL", record["detail"])

    def test_command_failure_preserves_configuration(self):
        record = self._grade(command=[sys.executable, "-c", "raise SystemExit(7)"],
                             evidence_class="command-adapter")
        self.assertEqual(record["status"], "BLOCKER")
        self.assertEqual(record["model_version"], "test-model")
        self.assertEqual(record["tool_policy"], "test-policy")
        self.assertEqual(record["budget"]["time_seconds"], 10)
        self.assertIn("exit 7", record["detail"])

    @unittest.skipUnless(os.name == "posix", "POSIX process-group boundary")
    def test_command_timeout_stops_descendant_writers(self):
        with tempfile.TemporaryDirectory() as name:
            checkout = Path(name)
            marker = checkout / "late-write"
            child = "import time; from pathlib import Path; time.sleep(0.7); Path('late-write').write_text('bad')"
            parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1]]); time.sleep(10)"
            with self.assertRaises(subprocess.TimeoutExpired):
                harness._run_command([sys.executable, "-c", parent, child], checkout, "", 0.15)
            time.sleep(0.8)
            self.assertFalse(marker.exists())

    def test_mutated_fixture_is_rejected_before_runtime_starts(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture = root / self.task["repo"]["root"]
            shutil.copytree(ROOT / self.task["repo"]["root"], fixture)
            (fixture / "ledger.py").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(harness.HarnessError, "fixture hash"):
                harness.grade_mode(root, [self.task], condition="NO_MEMORY", runtime="codex",
                                   repetition="test", grade="starter", evidence_class="live-runtime",
                                   tool_policy="test", model_version="test", command=None,
                                   codex_executable="must-not-run")

    def test_live_requires_explicit_model_before_adapter_import(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = harness.main(["--mode", "live", "--runtime", "codex",
                                 "--codex-executable", "codex-test", "--condition", "NO_MEMORY",
                                 "--task", self.task["task_id"]])
        self.assertEqual(code, 1)
        self.assertIn("requires --model-version", err.getvalue())

    def test_existing_result_is_rejected_before_live_execution(self):
        result_id = harness.make_result_id(self.task, "NO_MEMORY", "codex", "test",
                                           self.task["repo"]["commit"])
        with tempfile.TemporaryDirectory() as name:
            (Path(name) / f"{result_id}.json").write_text("{}\n", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                code = harness.main(["--mode", "live", "--runtime", "codex",
                                     "--codex-executable", "must-not-run", "--model-version", "test",
                                     "--condition", "NO_MEMORY", "--task", self.task["task_id"],
                                     "--repetition-id", "test", "--record-dir", name])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err.getvalue())

    def test_native_flag_cannot_masquerade_as_command_adapter(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = harness.main(["--mode", "command", "--runtime", "codex",
                                 "--codex-executable", "must-not-run"])
        self.assertEqual(code, 1)
        self.assertIn("requires --mode live --runtime codex", err.getvalue())

    def test_symlink_directories_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "target").mkdir()
            try:
                (root / "link").symlink_to(root / "target", target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(harness.HarnessError):
                harness.iter_files(root, ())


if __name__ == "__main__":
    unittest.main()
