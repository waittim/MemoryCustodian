import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "codex_runtime_test", ROOT / "benchmarks" / "runners" / "codex_runtime.py"
)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def jsonl(*events):
    return "\n".join(json.dumps(event) for event in events) + "\n"


START = {"type": "thread.started", "thread_id": "test-session"}
DONE = {
    "type": "turn.completed",
    "usage": {"input_tokens": 123, "output_tokens": 45, "cached_input_tokens": 20},
}


class CodexEventTests(unittest.TestCase):
    def test_completed_turn_counts_unique_tool_ids_and_usage(self):
        output = jsonl(
            START, {"type": "turn.started"},
            {"type": "item.started", "item": {"id": "tool-1", "type": "command_execution"}},
            {"type": "item.completed", "item": {"id": "tool-1", "type": "command_execution"}},
            {"type": "item.completed", "item": {"id": "tool-2", "type": "file_change"}},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": "done"}},
            DONE,
        )
        result = runtime.summarize_events(output)
        self.assertTrue(result["valid"])
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(result["total_input_tokens"], 123)
        self.assertEqual(result["total_output_tokens"], 45)
        self.assertEqual(result["cached_input_tokens"], 20)

    def test_malformed_or_failed_stream_never_counts_as_completed(self):
        invalid_streams = [
            "", "not json", jsonl([]), jsonl(START, {}, DONE),
            jsonl(DONE, START), jsonl(START, START, DONE), jsonl(START, DONE, DONE),
            jsonl({"type": "thread.started", "thread_id": ""}, DONE),
            jsonl(START, {"type": "turn.failed"}, DONE),
            jsonl(START, {"type": "error", "message": "raw error"}, DONE),
            jsonl(START, {"type": "item.completed", "item": []}, DONE),
            jsonl(START, {"type": "item.completed", "item": {"type": "command_execution"}}, DONE),
        ]
        for output in invalid_streams:
            with self.subTest(output=output):
                self.assertFalse(runtime.summarize_events(output)["valid"])

    def test_unobserved_usage_is_null_without_inventing_failure(self):
        for usage in (None, {}, {"input_tokens": True, "output_tokens": 2}):
            with self.subTest(usage=usage):
                result = runtime.summarize_events(jsonl(START, {"type": "turn.completed", "usage": usage}))
                self.assertTrue(result["valid"])
                self.assertIsNone(result["total_input_tokens"])
                self.assertIsNone(result["total_output_tokens"])
                self.assertIsNone(result["cached_input_tokens"])
        for cached in (None, -1, True, 124):
            with self.subTest(cached=cached):
                usage = {**DONE["usage"], "cached_input_tokens": cached}
                result = runtime.summarize_events(jsonl(START, {"type": "turn.completed", "usage": usage}))
                self.assertTrue(result["valid"])
                self.assertEqual(result["total_input_tokens"], 123)
                self.assertIsNone(result["cached_input_tokens"])

    def test_action_trace_keeps_only_normalized_diagnostic_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            checkout.mkdir()
            output = jsonl(
                START,
                {"type": "item.completed", "item": {
                    "type": "command_execution", "id": "command", "status": "completed", "exit_code": 0,
                    "command": "cat docs/memory/brief.md docs/manual/facts.md; echo PRIVATE_COMMAND",
                    "aggregated_output": "PRIVATE_OUTPUT",
                }},
                {"type": "item.completed", "item": {
                    "type": "file_change", "id": "change", "status": "completed",
                    "changes": [
                        {"path": str(checkout / "src.py"), "kind": "update"},
                        {"path": "answer.md", "kind": "add"},
                        {"path": "../escape.py", "kind": "delete"},
                        {"path": str(checkout.parent / "outside.py"), "kind": "update"},
                    ],
                }},
                {"type": "item.completed", "item": {
                    "type": "agent_message", "id": "message", "text": "PRIVATE_RESPONSE",
                }},
                {"type": "item.completed", "item": {
                    "type": "reasoning", "id": "reason", "text": "PRIVATE_REASONING",
                }}, DONE,
            )
            trace = runtime.summarize_events(output, checkout=checkout)["action_trace"]
            self.assertEqual(len(trace), 3)
            self.assertEqual(trace[0]["source_path_mentions"], ["docs/manual/facts.md", "docs/memory/brief.md"])
            self.assertEqual(trace[0]["aggregated_output_sha256"], hashlib.sha256(b"PRIVATE_OUTPUT").hexdigest())
            self.assertEqual(trace[1]["changes"], [{"path": "src.py", "kind": "update"}, {"path": "answer.md", "kind": "add"}])
            serialized = json.dumps(trace)
            for forbidden in (directory, "PRIVATE_COMMAND", "PRIVATE_OUTPUT", "PRIVATE_RESPONSE", "PRIVATE_REASONING", "escape.py", "outside.py"):
                self.assertNotIn(forbidden, serialized)


class CodexRuntimeTests(unittest.TestCase):
    def run_stub(self, checkout, *, stdout=None, returncode=0):
        process = Mock()
        process.communicate.return_value = (stdout or jsonl(START, DONE), "PRIVATE_STDERR")
        process.returncode = returncode
        return process

    def test_safe_argv_pinned_policy_and_no_raw_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            process = self.run_stub(checkout)
            prompt = "literal $(touch outside) `do-not-execute`; PRIVATE_PROMPT"
            with patch.object(runtime.shutil, "which", return_value="/opt/codex"), patch.object(
                runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "codex-cli 1.2.3\n", "")
            ), patch.object(runtime.subprocess, "Popen", return_value=process) as launch:
                result = runtime.run_codex(checkout, prompt, executable="codex", model="pinned-model", timeout=120)
            self.assertEqual(result["status"], "completed")
            argv = launch.call_args.args[0]
            self.assertIsInstance(argv, list)
            self.assertNotIn(prompt, argv)
            self.assertNotIn("shell", launch.call_args.kwargs)
            self.assertIn("--ignore-user-config", argv)
            self.assertIn("--ephemeral", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
            self.assertEqual(argv[argv.index("--model") + 1], "pinned-model")
            self.assertEqual(argv[argv.index("-C") + 1], str(checkout.resolve()))
            self.assertIn("sandbox_workspace_write.network_access=false", argv)
            self.assertIn("features.skip_host_skill_discovery=true", argv)
            self.assertEqual(process.communicate.call_args.kwargs, {"input": runtime.PROMPT_PREFIX + prompt, "timeout": 120})
            serialized = json.dumps(result)
            self.assertNotIn("PRIVATE_PROMPT", serialized)
            self.assertNotIn("PRIVATE_STDERR", serialized)
            self.assertNotIn(directory, serialized)
            self.assertFalse(result["runtime_metadata"]["raw_trace_retained"])
            self.assertEqual(result["metrics"]["total_input_tokens"], 123)

    def test_launch_requires_executable_model_positive_timeout(self):
        for executable_path, model, timeout in ((None, "model", 1), ("/opt/codex", "", 1), ("/opt/codex", "model", 0)):
            with self.subTest(values=(executable_path, model, timeout)), patch.object(
                runtime.shutil, "which", return_value=executable_path
            ), patch.object(runtime.subprocess, "Popen") as launch:
                result = runtime.run_codex(ROOT, "task", executable="codex", model=model, timeout=timeout)
            self.assertEqual(result["status"], "blocked")
            launch.assert_not_called()

    def test_version_probe_failure_is_a_blocker(self):
        for probe in (subprocess.TimeoutExpired("version", 10), subprocess.CompletedProcess([], 0, "other runtime", "")):
            kwargs = {"side_effect": probe} if isinstance(probe, Exception) else {"return_value": probe}
            with self.subTest(probe=probe), patch.object(runtime.shutil, "which", return_value="/opt/codex"), patch.object(
                runtime.subprocess, "run", **kwargs
            ), patch.object(runtime.subprocess, "Popen") as launch:
                result = runtime.run_codex(ROOT, "task", executable="codex", model="model", timeout=120)
            self.assertEqual(result["status"], "blocked")
            launch.assert_not_called()

    def test_process_failure_and_incomplete_events_are_blockers(self):
        for stdout, code in ((jsonl(START, DONE), 1), (jsonl(START), 0), ("invalid-json", 0)):
            with self.subTest(stdout=stdout, code=code), patch.object(runtime.shutil, "which", return_value="/opt/codex"), patch.object(
                runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", "")
            ), patch.object(runtime.subprocess, "Popen", return_value=self.run_stub(ROOT, stdout=stdout, returncode=code)):
                result = runtime.run_codex(ROOT, "task", executable="codex", model="model", timeout=120)
            self.assertEqual(result["status"], "blocked")

    def test_timeout_or_invalid_encoding_stops_runtime_group(self):
        for error in (subprocess.TimeoutExpired("codex", 1), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")):
            process = Mock()
            process.communicate.side_effect = error
            with self.subTest(error=type(error).__name__), patch.object(runtime.shutil, "which", return_value="/opt/codex"), patch.object(
                runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", "")
            ), patch.object(runtime.subprocess, "Popen", return_value=process), patch.object(runtime, "_stop_process") as stop:
                result = runtime.run_codex(ROOT, "task", executable="codex", model="model", timeout=1)
            self.assertEqual(result["status"], "blocked")
            stop.assert_called_once_with(process)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group termination")
    def test_timeout_cleanup_escalates_for_stubborn_process_group(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired("codex", 2), ("", "")]
        with patch.object(runtime.os, "killpg") as kill:
            runtime._stop_process(process)
        self.assertEqual(kill.call_args_list[0].args, (12345, signal.SIGTERM))
        self.assertEqual(kill.call_args_list[1].args, (12345, signal.SIGKILL))


if __name__ == "__main__":
    unittest.main()
