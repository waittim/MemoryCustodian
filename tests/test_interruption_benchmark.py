import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners import interruption as experiment


START = {"type": "thread.started", "thread_id": "prefix-session"}
DONE = {"type": "turn.completed", "usage": {
    "input_tokens": 120, "output_tokens": 12, "cached_input_tokens": 50,
}}


def tool(identifier, **fields):
    return {"type": "item.completed", "item": {
        "id": identifier, "type": "command_execution", "exit_code": 0, **fields,
    }}


class ObservationTests(unittest.TestCase):
    def test_checkpoint_excludes_reasoning_raw_commands_and_tool_output(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            observed = experiment.Observations(checkout)
            for event in (
                START,
                tool("read", command="cat PRIVATE_ARGUMENT", aggregated_output="PRIVATE_OUTPUT"),
                {"type": "item.completed", "item": {
                    "id": "private", "type": "reasoning", "text": "PRIVATE_REASONING",
                }},
                {"type": "item.completed", "item": {
                    "id": "visible", "type": "agent_message",
                    "text": f"Inspected {checkout}/source.py; tests still need running.",
                }},
                {"type": "item.completed", "item": {
                    "id": "edit", "type": "file_change", "changes": [
                        {"path": str(checkout / "source.py")},
                        {"path": "../outside.py"},
                        {"path": str(checkout.parent / "external.py")},
                        {"path": "C:\\outside.py"},
                    ],
                }},
            ):
                observed.accept(event)
            summary = experiment.checkpoint_summary(
                observed.summary(), observed.messages,
                {"source.py": "before", "removed.py": "old", "same.py": "same"},
                {"source.py": "after", "same.py": "same"},
            )
            self.assertEqual(summary["changed_files"], {"source.py": "after"})
            self.assertEqual(summary["deleted_files"], ["removed.py"])
            self.assertEqual(summary["completed_tools"][-1]["changed_paths"], ["source.py"])
            serialized = json.dumps(summary)
            self.assertIn("tests still need running", serialized)
            for private in (directory, "PRIVATE_ARGUMENT", "PRIVATE_OUTPUT", "PRIVATE_REASONING", "outside.py", "external.py"):
                self.assertNotIn(private, serialized)
            self.assertIsNone(observed.summary()["repeated_file_reads"])

    def test_invalid_or_failed_events_cannot_supply_successful_contract(self):
        cases = (
            [DONE], [START, START], [START, {"type": "error"}],
            [START, {"type": "turn.failed"}], [START, DONE, DONE],
            [START, {"type": "item.completed", "item": []}],
            [START, {"type": "item.completed", "item": {"type": "command_execution"}}],
        )
        for events in cases:
            with self.subTest(events=events):
                observations = experiment.Observations(Path("/tmp/fixture"))
                for event in events:
                    observations.accept(event)
                self.assertFalse(observations.summary()["event_contract_valid"])

    def test_argument_policy_preserves_sandbox_and_explicit_resume_identity(self):
        checkout = Path("/tmp/fixture")
        commands = {
            "fresh": experiment.argv("codex", "fixed-model", checkout),
            "prefix": experiment.argv("codex", "fixed-model", checkout, persistent=True),
            "native": experiment.argv("codex", "fixed-model", checkout, resume="specific-session"),
        }
        for command in commands.values():
            self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
            self.assertIn('approval_policy="never"', command)
            self.assertIn("sandbox_workspace_write.network_access=false", command)
            self.assertIn("features.skip_host_skill_discovery=true", command)
            self.assertIn("--ignore-user-config", command)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertIn("--ephemeral", commands["fresh"])
        self.assertNotIn("--ephemeral", commands["prefix"])
        self.assertNotIn("--ephemeral", commands["native"])
        self.assertEqual(commands["native"][-3:], ["resume", "specific-session", "-"])
        self.assertNotIn("--last", commands["native"])


@unittest.skipUnless(os.name == "posix", "experiment uses POSIX process groups")
class StreamingTests(unittest.TestCase):
    def run_script(self, checkout, script, **kwargs):
        return experiment.stream_run(
            [sys.executable, "-u", "-c", script], checkout,
            "literal input $(must-not-execute)", timeout=kwargs.pop("timeout", 3), **kwargs,
        )

    def test_forced_boundary_terminates_descendant_before_it_can_write(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            marker = checkout / "late-write"
            child = "import pathlib,time;time.sleep(0.6);pathlib.Path('late-write').write_text('escaped')"
            events = (START, tool("one"), tool("two"))
            script = (
                "import json,subprocess,sys,time\n"
                "sys.stdin.read()\n"
                f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
                f"events = {events!r}\n"
                "for event in events: print(json.dumps(event), flush=True)\n"
                "time.sleep(10)\n"
            )
            result, _ = self.run_script(checkout, script, interrupt_after=2)
            self.assertEqual(result["status"], "INTERRUPTED")
            self.assertEqual(len(result["completed_tools"]), 2)
            self.assertEqual(result["completion_events"], 0)
            self.assertEqual(result["thread_id"], "prefix-session")
            self.assertIsNone(result["total_input_tokens"])
            time.sleep(0.75)
            self.assertFalse(marker.exists(), "an interrupted runtime left a writer alive")

    def test_complete_turn_observes_usage_without_retaining_raw_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            events = (START, tool("one", command="PRIVATE_COMMAND", aggregated_output="PRIVATE_OUTPUT"), DONE)
            script = (
                "import json,sys\nsys.stdin.read()\n"
                f"events = {events!r}\n"
                "for event in events: print(json.dumps(event), flush=True)\n"
                "print('PRIVATE_STDERR', file=sys.stderr)\n"
            )
            result, messages = self.run_script(Path(directory), script)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["total_input_tokens"], 120)
            self.assertEqual(result["total_output_tokens"], 12)
            self.assertEqual(result["tool_calls"], 1)
            self.assertEqual(messages, [])
            self.assertFalse(result["raw_trace_retained"])
            serialized = json.dumps(result)
            for raw in ("PRIVATE_COMMAND", "PRIVATE_OUTPUT", "PRIVATE_STDERR", directory):
                self.assertNotIn(raw, serialized)

    def test_timeout_and_invalid_stream_are_blockers(self):
        scripts = (
            "import sys,time;sys.stdin.read();time.sleep(10)",
            "import sys;sys.stdin.read();print('not json', flush=True)",
            "import json,sys;sys.stdin.read();print(json.dumps({'type':'thread.started','thread_id':'x'}),flush=True)",
        )
        for script in scripts:
            with self.subTest(script=script), tempfile.TemporaryDirectory() as directory:
                result, _ = self.run_script(Path(directory), script, timeout=0.2)
                self.assertEqual(result["status"], "BLOCKER")


class PairingTests(unittest.TestCase):
    TASK = {"task_id": "synthetic", "task_version": 1, "task_prompt": "Finish source.py",
            "repo": {"commit": "fixture-hash"}}

    def prepare(self, root, task, condition, checkout):
        checkout.mkdir(parents=True)
        (checkout / "source.py").write_text("starter", encoding="utf-8")

    def test_each_condition_restores_common_snapshot_and_native_identity(self):
        starts = []
        prompts = []
        def stream(command, checkout, prompt, **kwargs):
            prompts.append(prompt)
            if kwargs.get("interrupt_after"):
                (checkout / "source.py").write_text("partial", encoding="utf-8")
                return {"status": "INTERRUPTED", "thread_id": "prefix-session", "completed_tools": []}, ["Read source.py"]
            starts.append((checkout / "source.py").read_text(encoding="utf-8"))
            (checkout / "source.py").write_text("finished", encoding="utf-8")
            return {"status": "COMPLETED", "thread_id": "prefix-session" if "resume" in command else "fresh"}, []
        def grade(root, task, checkout):
            return {"status": "PASS" if (checkout / "source.py").read_text(encoding="utf-8") == "finished" else "FAIL"}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            experiment, "prepare_checkout", side_effect=self.prepare
        ), patch.object(experiment, "stream_run", side_effect=stream), patch.object(experiment, "evaluate", side_effect=grade):
            row = experiment.run_pair(ROOT, self.TASK, Path(directory), executable="codex", model="fixed",
                                      repetition=1, order_offset=1, timeout=3)
        self.assertEqual(row["status"], "COMPLETE")
        self.assertEqual(starts, ["partial"] * 3)
        self.assertEqual([cell["condition"] for cell in row["conditions"]],
                         ["OBSERVABLE_CHECKPOINT", "NATIVE_RESUME", "FRESH"])
        self.assertEqual(len({cell["starting_tree_sha256"] for cell in row["conditions"]}), 1)
        self.assertIn("Observable progress summary", prompts[1])
        self.assertNotIn("Observable progress summary", prompts[2])
        self.assertNotIn("Observable progress summary", prompts[3])

    def test_already_solved_prefix_is_inapplicable_not_a_recovery_win(self):
        prefix = {"status": "INTERRUPTED", "thread_id": "prefix-session", "completed_tools": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            experiment, "prepare_checkout", side_effect=self.prepare
        ), patch.object(experiment, "stream_run", return_value=(prefix, [])) as stream, patch.object(
            experiment, "evaluate", return_value={"status": "PASS"}
        ):
            row = experiment.run_pair(ROOT, self.TASK, Path(directory), executable="codex", model="fixed",
                                      repetition=1, order_offset=0, timeout=3)
        self.assertEqual(row["status"], "INAPPLICABLE")
        self.assertEqual(row["conditions"], [])
        self.assertEqual(stream.call_count, 1)

    def test_unavailable_prefix_grading_is_blocker_and_does_not_resume(self):
        prefix = {"status": "INTERRUPTED", "thread_id": "prefix-session", "completed_tools": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            experiment, "prepare_checkout", side_effect=self.prepare
        ), patch.object(experiment, "stream_run", return_value=(prefix, [])) as stream, patch.object(
            experiment, "evaluate", return_value={"status": "BLOCKER"}
        ):
            row = experiment.run_pair(ROOT, self.TASK, Path(directory), executable="codex", model="fixed",
                                      repetition=1, order_offset=0, timeout=3)
        self.assertEqual(row["status"], "BLOCKER")
        self.assertEqual(row["conditions"], [])
        self.assertEqual(stream.call_count, 1)

    def test_native_session_identity_mismatch_is_not_a_graded_task_failure(self):
        prefix = {"status": "INTERRUPTED", "thread_id": "prefix-session", "completed_tools": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            experiment, "prepare_checkout", side_effect=self.prepare
        ), patch.object(experiment, "stream_run", side_effect=[
            (prefix, []), ({"status": "COMPLETED", "thread_id": "wrong-session"}, []),
            ({"status": "COMPLETED", "thread_id": "fresh-1"}, []),
            ({"status": "COMPLETED", "thread_id": "fresh-2"}, []),
        ]), patch.object(experiment, "evaluate", return_value={"status": "FAIL"}) as grade:
            row = experiment.run_pair(ROOT, self.TASK, Path(directory), executable="codex", model="fixed",
                                      repetition=1, order_offset=2, timeout=3)
        self.assertEqual(row["status"], "BLOCKER")
        self.assertEqual(row["conditions"][0]["condition"], "NATIVE_RESUME")
        self.assertEqual(row["conditions"][0]["status"], "BLOCKER")
        self.assertEqual(grade.call_count, 3, "wrong native identity must not reach the grader")

    def test_native_cumulative_tokens_are_not_reported_as_recovery_cost(self):
        def stream(command, checkout, prompt, **kwargs):
            if kwargs.get("interrupt_after"):
                return {"status": "INTERRUPTED", "thread_id": "prefix-session",
                        "completed_tools": [], "total_input_tokens": None,
                        "total_output_tokens": None, "cached_input_tokens": None}, []
            native = "resume" in command
            return {"status": "COMPLETED", "thread_id": "prefix-session" if native else "fresh",
                    "total_input_tokens": 27247 if native else 13611,
                    "total_output_tokens": 12 if native else 5,
                    "cached_input_tokens": 22000 if native else 10000}, []
        with tempfile.TemporaryDirectory() as directory, patch.object(
            experiment, "prepare_checkout", side_effect=self.prepare
        ), patch.object(experiment, "stream_run", side_effect=stream), patch.object(
            experiment, "evaluate", return_value={"status": "FAIL"}
        ):
            row = experiment.run_pair(ROOT, self.TASK, Path(directory), executable="codex", model="fixed",
                                      repetition=1, order_offset=0, timeout=3)
        self.assertEqual(row["status"], "COMPLETE")
        native = next(cell["runtime"] for cell in row["conditions"] if cell["condition"] == "NATIVE_RESUME")
        self.assertEqual(native["runtime_reported_total_input_tokens"], 27247)
        self.assertEqual(native["runtime_reported_total_output_tokens"], 12)
        self.assertEqual(native["runtime_reported_cached_input_tokens"], 22000)
        for key in ("total_input_tokens", "total_output_tokens", "cached_input_tokens"):
            self.assertIsNone(native[key], "a missing prefix baseline cannot yield post-resume token cost")
        self.assertIn("session cumulative", native["token_usage_scope"])
        for cell in row["conditions"]:
            if cell["condition"] != "NATIVE_RESUME":
                self.assertEqual(cell["runtime"]["total_input_tokens"], 13611)
                self.assertEqual(cell["runtime"]["total_output_tokens"], 5)
                self.assertEqual(cell["runtime"]["cached_input_tokens"], 10000)
                self.assertEqual(cell["runtime"]["token_usage_scope"], "recovery session")

    def test_infrastructure_grading_blockers_remain_blockers(self):
        for visible, oracle in (("BLOCKER", "PASS"), ("PASS", "BLOCKER"), ("FAIL", "BLOCKER")):
            with self.subTest(visible=visible, oracle=oracle), patch.object(
                experiment, "command_for", return_value=["test"]
            ), patch.object(experiment, "run_visible_tests", return_value=visible), patch.object(
                experiment, "grade_checkout", return_value={"status": oracle, "failure_labels": []}
            ):
                result = experiment.evaluate(ROOT, self.TASK, Path("/tmp/fixture"))
                self.assertEqual(result["status"], "BLOCKER")


if __name__ == "__main__":
    unittest.main()
