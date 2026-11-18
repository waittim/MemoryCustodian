"""Offline proofs for the live installed-Skill harness; never live evidence."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.runners import installed_skill_live as smoke

SPEC = importlib.util.spec_from_file_location("installed_skill_eval_cli_tests", ROOT / "scripts/run-installed-skill-eval.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def event(item, kind="item.completed"):
    return {"type": kind, "item": item}


def read_event(*, route="COMPLETE", task="implementation", output=True):
    payload = {"output_schema_version": 1, "protocol_version": "0.8", "command": "read",
               "status": "PASS" if route == "COMPLETE" else "FAIL",
               "exit_class": "success" if route == "COMPLETE" else "domain-failure",
               "data": {"routing_completeness": route, "canonical_task": task,
                        "normalized_paths": ["src/account.py"] if route == "COMPLETE" else []}}
    return event({"type": "command_execution", "id": "read",
                  "command": smoke.CLI + " read --strict-routing --format json",
                  "aggregated_output": json.dumps(payload) if output else "not a CLI result",
                  "exit_code": 0 if route == "COMPLETE" else 1})


def stream(*events):
    return "\n".join(json.dumps(value) for value in events) + "\n"


def proof(*events):
    skill = event({"type": "command_execution", "id": "skill", "command": "cat " + smoke.SKILL,
                   "aggregated_output": "name: memory-custodian\n## Hard Gate", "exit_code": 0})
    return smoke.observe(stream(skill, *events))


def runtime(observations):
    return {"status": "COMPLETED", "evidence_class": "offline-runtime-stub", "observations": observations}


class InstalledSkillObservationTests(unittest.TestCase):
    def test_single_cli_recognition_rejects_composite_help_and_substitutions(self):
        help_command = smoke.CLI + " add --help"
        self.assertEqual(smoke._cli_completion(help_command, "usage: memory-custodian", 0)[0], "readonly-help")
        wrapped = "/bin/sh -c " + shlex.quote(help_command)
        self.assertEqual(smoke._cli_completion(wrapped, "usage: memory-custodian", 0)[0], "readonly-help")
        for command in (
            help_command + "; python -c 'write_text()'",
            help_command + " && " + smoke.CLI + " add value --candidate",
            help_command + " > help.txt", help_command + "\necho another-command",
            "$(echo " + smoke.CLI + ") add --help",
            smoke.CLI + " subject add item $FLAGS",
            smoke.CLI + " subject add item ${FLAGS}",
            smoke.CLI + " subject add item *",
            smoke.CLI + " subject add item [a-z]*",
            smoke.CLI + " subject add item {--apply,--help}",
            smoke.CLI + " subject add item # --apply",
        ):
            with self.subTest(command=command):
                self.assertIsNone(smoke._single_cli_arguments(command))
                self.assertEqual(smoke._cli_completion(command, "usage: memory-custodian", 0)[0], "uncertain")

    def test_cli_option_terminators_abbreviations_and_equals_previews_are_conservative(self):
        document = json.dumps({"output_schema_version": 1, "protocol_version": "0.8", "command": "add",
                               "status": "PASS", "exit_class": "success",
                               "data": {"plan": {"public_plan_schema_version": 1}}})
        for suffix in ("add --supersedes=MC-CON-example value", "add --from-legacy=constraints.md:0"):
            with self.subTest(suffix=suffix):
                self.assertEqual(smoke._cli_completion(smoke.CLI + " " + suffix, document, 0)[0], "readonly-preview")
        for suffix in (
            "add --type decision --candidate -- --help", "subject add value --ap", "subject add value --app",
            "add --sup=MC-CON-example value", "add --from-l=constraints.md:0",
        ):
            with self.subTest(suffix=suffix):
                self.assertEqual(smoke._cli_completion(smoke.CLI + " " + suffix, document, 0)[0], "uncertain")
        unknown = smoke.CLI + " subject rename MC-SUBJ-example Replacement"
        observed = proof(event({"type": "command_execution", "id": "unknown", "command": unknown}, "item.started"),
                         event({"type": "command_execution", "id": "unknown", "command": unknown,
                                "aggregated_output": "opaque CLI result", "exit_code": 0}))
        self.assertEqual(observed["mutation_sequences"], [])
        self.assertEqual(observed["uncertain_mutation_sequences"], [2])
        missing_start = proof(event({"type": "command_execution", "id": "unknown", "command": unknown,
                                     "aggregated_output": "opaque CLI result", "exit_code": 0}))
        self.assertEqual(missing_start["uncertain_mutation_sequences"], [2])
        self.assertTrue(missing_start["unbounded_mutation"])

    def test_error_diagnostics_keep_only_allowlisted_categories_status_and_counts(self):
        samples = (
            ({"error": {"code": "invalid_api_key", "message": "PRIVATE_TOKEN https://private.invalid/?key=sk-secret"}}, {"auth"}),
            ({"error": {"code": "rate_limit_exceeded", "http_status_code": 429}}, {"rate-limit"}),
            ({"error": {"message": "Connection reset by peer PRIVATE_TOKEN"}}, {"transport"}),
            ({"error": {"message": "PRIVATE_TOKEN", "status_code": 503}}, {"provider"}),
            ({"error": {"codex_error_info": {"http_connection_failed": {"http_status_code": 502}}}}, {"transport", "provider"}),
            ({"error": {"message": "PRIVATE_TOKEN"}}, {"unknown"}),
        )
        for payload, expected in samples:
            with self.subTest(expected=expected):
                value = {"type": "turn.failed", "status": "failed", **payload,
                         "headers": {"Authorization": "Bearer PRIVATE_TOKEN"}, "url": "https://private.invalid/"}
                result = smoke.diagnostics(stream(value), "", exit_code=1)
                self.assertEqual(set(result["categories"]), expected)
                self.assertEqual(result["event_kind_counts"], {"turn.failed": 1})
                self.assertEqual(result["error_events"][0]["status"], "failed")
                self.assertEqual(result["exit_code"], 1)
                encoded = json.dumps(result)
                for forbidden in ("PRIVATE_TOKEN", "https://", "Authorization", "Bearer", "sk-secret", "invalid_api_key", "http_connection_failed"):
                    self.assertNotIn(forbidden, encoded)

    def test_diagnostics_reject_unknown_metadata_and_do_not_invent_success_errors(self):
        values = stream({"type": "PRIVATE_EVENT /private/path"},
                        {"type": "error", "status": {"PRIVATE_STATUS": "secret"},
                         "error": {"message": "opaque", "http_status_code": True}})
        result = smoke.diagnostics(values, "opaque PRIVATE_STDERR /private/path", exit_code=1)
        self.assertEqual(result["event_kind_counts"], {"error": 1, "other": 1})
        self.assertEqual(result["categories"], ["unknown"])
        self.assertNotIn("status", result["error_events"][0])
        self.assertEqual(result["error_events"][0]["http_status_codes"], [])
        for forbidden in ("PRIVATE_EVENT", "PRIVATE_STATUS", "PRIVATE_STDERR", "/private/path"):
            self.assertNotIn(forbidden, json.dumps(result))
        healthy = smoke.diagnostics(stream({"type": "turn.completed"}), "rate limit debug note", exit_code=0)
        self.assertEqual(healthy["categories"], [])
        malformed = smoke.diagnostics("PRIVATE_BAD_JSON\n", "", exit_code=1)
        self.assertEqual(malformed["malformed_jsonl_lines"], 1)
        self.assertEqual(malformed["categories"], ["unknown"])
        bounded = smoke.diagnostics(stream(*[{"type": "error", "message": "opaque"}] * 40), "", exit_code=1)
        self.assertEqual(len(bounded["error_events"]), 32)
        self.assertTrue(bounded["error_events_truncated"])
        self.assertEqual(bounded["event_kind_counts"]["error"], 40)

    def test_failed_runtime_retains_safe_diagnostics_without_turn_completion(self):
        output = stream({"type": "thread.started", "thread_id": "offline-diagnostic"},
                        {"type": "turn.failed", "error": {"message": "stream disconnected before completion PRIVATE_TOKEN"}})
        process = Mock()
        process.communicate.return_value = (output, "Transport error PRIVATE_STDERR")
        process.returncode = 1
        process.poll.return_value = 1
        with tempfile.TemporaryDirectory() as name, patch.object(smoke.subprocess, "Popen", return_value=process):
            directory = Path(name)
            result = smoke.run_runtime(["offline-stub"], directory, directory, "PRIVATE_PROMPT", timeout=1)
        self.assertEqual(result["status"], "BLOCKER")
        self.assertEqual(result["completion_events"], 0)
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["diagnostics"]["categories"], ["transport"])
        self.assertEqual(result["diagnostics"]["event_kind_counts"]["turn.failed"], 1)
        for forbidden in ("PRIVATE_TOKEN", "PRIVATE_STDERR", "PRIVATE_PROMPT"):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_partial_timeout_and_launch_failures_remain_blockers(self):
        partial = stream({"type": "error", "message": "authentication failed PRIVATE_TOKEN"}).encode()
        process = Mock()
        process.communicate.side_effect = subprocess.TimeoutExpired("offline-stub", 1, output=partial, stderr=b"PRIVATE_STDERR")
        process.returncode = -15
        process.poll.return_value = -15
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            with patch.object(smoke.subprocess, "Popen", return_value=process), patch.object(smoke, "_stop_process"):
                result = smoke.run_runtime(["offline-stub"], directory, directory, "prompt", timeout=1)
            self.assertEqual(result["status"], "BLOCKER")
            self.assertEqual(result["capture_scope"], "partial-before-timeout")
            self.assertEqual(result["event_stream_sha256"], smoke.sha(partial))
            self.assertEqual(set(result["diagnostics"]["categories"]), {"timeout", "auth"})
            self.assertEqual(result["exit_code"], -15)
            self.assertNotIn("completion_events", result)
            with patch.object(smoke.subprocess, "Popen", side_effect=OSError(13, "PRIVATE_PATH /private/key")):
                launch = smoke.run_runtime(["offline-stub"], directory, directory, "prompt", timeout=1)
            self.assertEqual(launch["status"], "BLOCKER")
            self.assertEqual(launch["diagnostics"]["categories"], ["launch"])
            for forbidden in ("PRIVATE_TOKEN", "PRIVATE_STDERR", "PRIVATE_PATH", "/private/key"):
                self.assertNotIn(forbidden, json.dumps([result, launch]))

    def test_command_mentions_alone_never_establish_strict_read(self):
        self.assertEqual(proof(read_event(output=False))["strict_reads"], [])
        malformed = read_event()
        document = json.loads(malformed["item"]["aggregated_output"])
        for key, value in (("output_schema_version", 99), ("output_schema_version", True),
                           ("protocol_version", "unknown"), ("command", "echo"),
                           ("status", "FAIL"), ("exit_class", "domain-failure")):
            with self.subTest(key=key):
                changed = copy.deepcopy(document)
                changed[key] = value
                malformed["item"]["aggregated_output"] = json.dumps(changed)
                self.assertEqual(proof(malformed)["strict_reads"], [])
        wrong_exit = read_event()
        wrong_exit["item"]["exit_code"] = 1
        self.assertEqual(proof(wrong_exit)["strict_reads"], [])
        observed = proof(read_event())
        self.assertTrue(observed["skill_read_sequences"])
        self.assertEqual(observed["strict_reads"][0]["routing"], "COMPLETE")

    def test_raw_payloads_reasoning_and_machine_paths_are_not_retained(self):
        values = (
            event({"type": "reasoning", "id": "r", "text": "PRIVATE_REASONING"}),
            event({"type": "agent_message", "id": "m", "text": "PRIVATE_MESSAGE /private/local/path"}),
            event({"type": "command_execution", "id": "c", "command": "echo PRIVATE_COMMAND /private/local/path",
                   "aggregated_output": "PRIVATE_OUTPUT", "exit_code": 0}),
        )
        encoded = json.dumps(smoke.observe(stream(*values)))
        for text in ("PRIVATE_REASONING", "PRIVATE_MESSAGE", "PRIVATE_COMMAND", "PRIVATE_OUTPUT", "/private/local/path"):
            self.assertNotIn(text, encoded)
        self.assertIn("text_sha256", encoded)
        self.assertIn("command_sha256", encoded)
        forbidden = proof(event({"type": "web_search", "id": "web"}))
        self.assertTrue(forbidden["forbidden_external_tool"])

    def test_runtime_policy_keeps_manual_project_skill_available(self):
        checkout, state = Path("/tmp/fixture"), Path("/tmp/fixture-state")
        args = smoke.runtime_argv("codex", "pinned", checkout, state)
        self.assertEqual(args[args.index("--sandbox") + 1], "workspace-write")
        self.assertIn("sandbox_workspace_write.network_access=false", args)
        self.assertIn("features.skip_host_skill_discovery=true", args)
        self.assertIn("skills.bundled.enabled=false", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--ephemeral", args)
        self.assertNotIn("skills", [args[index + 1] for index, item in enumerate(args[:-1]) if item == "--disable"])
        self.assertFalse(any("dangerously" in item for item in args))
        before = {key: os.environ.get(key) for key in ("HOME", "CODEX_HOME")}
        actual = smoke.environment(state)
        self.assertEqual({key: actual.get(key) for key in before}, before)
        self.assertEqual({key: os.environ.get(key) for key in before}, before)

    def test_fake_runtime_cannot_implicitly_become_live_and_timeout_blocks(self):
        output = stream({"type": "thread.started", "thread_id": "offline-stub"},
                        {"type": "turn.started"},
                        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
        process = Mock()
        process.communicate.return_value = (output, "PRIVATE_STDERR")
        process.returncode = 0
        process.poll.return_value = 0
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            with patch.object(smoke.subprocess, "Popen", return_value=process):
                result = smoke.run_runtime(["offline-stub"], directory, directory, "PRIVATE_PROMPT", timeout=1)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["evidence_class"], "offline-runtime-stub")
            record = smoke.make_record({"task_id": "unit-stub"}, result, {"status": "PASS"}, {})
            self.assertEqual(record["evidence_class"], "offline-runtime-stub")
            for forbidden in ("PRIVATE_PROMPT", "PRIVATE_STDERR", name):
                self.assertNotIn(forbidden, json.dumps(record))
            process.communicate.side_effect = subprocess.TimeoutExpired("offline-stub", 1)
            with patch.object(smoke.subprocess, "Popen", return_value=process), patch.object(smoke, "_stop_process") as stop:
                blocked = smoke.run_runtime(["offline-stub"], directory, directory, "prompt", timeout=1)
            self.assertEqual(blocked["status"], "BLOCKER")
            stop.assert_called_once_with(process)


@unittest.skipUnless(os.name == "posix", "fixture installation uses a real POSIX bundled wrapper")
class InstalledSkillFixtureTests(unittest.TestCase):
    def test_real_readonly_controls_then_read_then_write_and_uncertain_boundaries(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            checkout, state = base / "project", base / "state"
            fixture = smoke.prepare_fixture(ROOT, checkout, state, "unconfirmed-observation")
            inbox = checkout / "docs/memory/inbox.md"
            initial_inbox = inbox.read_bytes()
            add_args = ["add", "Retries might improve throughput.", "--type", "decision", "--candidate", "--evidence", "agent-observed"]
            read_args = ["read", "--task", "maintenance", "--path", "docs/memory/inbox.md", "--strict-routing"]

            def call(identifier, arguments):
                end = arguments.index("--") if "--" in arguments else len(arguments)
                arguments = [*arguments[:end], "--project-root", ".", "--format", "json", *arguments[end:]]
                command = shlex.join([smoke.CLI, *arguments])
                result = subprocess.run([str(checkout / smoke.CLI), *arguments], cwd=checkout,
                                        env=smoke.environment(state), text=True, capture_output=True,
                                        timeout=30, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return (
                    event({"type": "command_execution", "id": identifier, "command": command}, "item.started"),
                    event({"type": "command_execution", "id": identifier, "command": command,
                           "aggregated_output": result.stdout, "exit_code": 0}),
                )

            literal_help = call("literal-help", ["add", "--type", "decision", "--candidate", "--evidence", "agent-observed", "--", "--help"])
            self.assertNotEqual(inbox.read_bytes(), initial_inbox)  # This really wrote a candidate named --help.
            literal_observed = proof(*literal_help)
            self.assertEqual(literal_observed["readonly_cli_sequences"], [])
            self.assertTrue(literal_observed["uncertain_mutation_sequences"])
            inbox.write_bytes(initial_inbox)
            help_events = call("help", ["add", "--help"])
            preview_events = call("preview", ["subject", "add", "Readonly preview", "--kind", "concept", "--evidence", "user-confirmed"])
            self.assertEqual(smoke.fingerprints(checkout), fixture["initial_files"])
            read_events = call("read", read_args)
            add_events = call("write", add_args)
            observed = proof(*help_events, *preview_events, *read_events, *add_events)
            result = smoke.grade(checkout, state, fixture, runtime(observed))
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(observed["observations_schema_version"], 2)
            self.assertEqual(len(observed["mutation_sequences"]), 3)  # Preserve legacy possible-event meaning.
            self.assertEqual(len(observed["confirmed_mutation_sequences"]), 1)
            self.assertEqual(observed["uncertain_mutation_sequences"], [])
            first_read = observed["strict_reads"][0]["sequence"]
            self.assertLess(min(observed["mutation_sequences"]), first_read)  # Old earliest-possible rule falsely fails.
            actions = [row.get("cli_action") for row in observed["events"]]
            self.assertIn("readonly-help", actions)
            self.assertIn("readonly-preview", actions)
            self.assertIn("confirmed-write", actions)

            # A fresh starting artifact state, then an actual installed-CLI write
            # before the actual strict read, still fails.
            inbox.write_bytes(initial_inbox)
            early_add = call("early-write", add_args)
            late_read = call("late-read", read_args)
            violation = smoke.grade(checkout, state, fixture, runtime(proof(*early_add, *late_read)))
            self.assertEqual(violation["status"], "FAIL", violation)
            self.assertFalse(violation["checks"]["strict_read_before_mutation"])

            # A compound help+write is not a single read-only invocation. Its
            # ambiguous execution cannot earn PASS, even with valid final data.
            inbox.write_bytes(initial_inbox)
            compound = shlex.join([smoke.CLI, "add", "--help"]) + "; " + shlex.join(
                [smoke.CLI, *add_args, "--project-root", ".", "--format", "json"]
            )
            completed = subprocess.run(["/bin/sh", "-c", compound], cwd=checkout, env=smoke.environment(state),
                                       capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            compound_events = (
                event({"type": "command_execution", "id": "compound", "command": compound}, "item.started"),
                event({"type": "command_execution", "id": "compound", "command": compound,
                       "aggregated_output": completed.stdout, "exit_code": 0}),
            )
            after_compound_read = call("after-compound", read_args)
            ambiguous = smoke.grade(checkout, state, fixture, runtime(proof(*compound_events, *after_compound_read)))
            self.assertEqual(ambiguous["status"], "REVIEW", ambiguous)
            self.assertIsNone(ambiguous["checks"]["strict_read_before_mutation"])

            # A complex but genuinely read-only command is left uncertain; it
            # cannot silently certify a later write as having obeyed ordering.
            for unknown_command in (smoke.CLI + " add --help && true", smoke.CLI + " subject rename MC-SUBJ-example Replacement"):
                inbox.write_bytes(initial_inbox)
                early_unknown = (
                    event({"type": "command_execution", "id": "unknown", "command": unknown_command}, "item.started"),
                    event({"type": "command_execution", "id": "unknown", "command": unknown_command,
                           "aggregated_output": "opaque CLI result", "exit_code": 0}),
                )
                new_read = call("new-read", read_args)
                new_add = call("new-write", add_args)
                uncertain = smoke.grade(checkout, state, fixture, runtime(proof(*early_unknown, *new_read, *new_add)))
                self.assertEqual(uncertain["status"], "REVIEW", uncertain)
                self.assertTrue(all(value for key, value in uncertain["checks"].items() if key != "strict_read_before_mutation"))
            unknown_without_start = event({"type": "command_execution", "id": "unbounded",
                                           "command": smoke.CLI + " subject rename MC-SUBJ-example Replacement",
                                           "aggregated_output": "opaque CLI result", "exit_code": 0})
            unbounded = smoke.grade(checkout, state, fixture, runtime(proof(unknown_without_start, *new_read, *new_add)))
            self.assertEqual(unbounded["status"], "REVIEW", unbounded)
            for secret in ("Readonly preview", "Retries might improve throughput.", name):
                self.assertNotIn(secret, json.dumps(observed))

    def test_controller_records_only_explicit_subset_and_rejects_duplicates(self):
        from contextlib import redirect_stderr, redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            selected = ["missing-scope", "unconfirmed-observation"]
            args = ["--codex-executable", sys.executable, "--model-version", "test-model", "--tasks", *selected,
                    "--record-dir", str(base / "records"), "--report-file", str(base / "report.md")]
            with patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "codex-cli test-stub", "")), patch.object(
                cli, "prepare_fixture", side_effect=lambda root, checkout, state, task: {"task_id": task}
            ) as prepare, patch.object(cli, "run_runtime", side_effect=[dict(runtime(proof()), thread_id="offline-" + task) for task in selected]), patch.object(
                cli, "grade", return_value={"status": "PASS"}
            ), redirect_stdout(io.StringIO()):
                code = cli.main(args)
            self.assertEqual(code, 2)  # Offline stubs cannot produce live PASS.
            self.assertEqual([call.args[-1] for call in prepare.call_args_list], selected)
            metadata = json.loads((base / "records/experiment.json").read_text())
            self.assertEqual(metadata["tasks"], selected)
            self.assertEqual(metadata["diagnostics_schema_version"], 1)
            self.assertEqual(metadata["plan"], smoke.OBSERVER_PLAN)
            self.assertEqual(metadata["observations_schema_version"], 2)
            records = [json.loads(path.read_text()) for path in (base / "records").glob("installed-skill__*.json")]
            self.assertEqual({record["task_id"] for record in records}, set(selected))
            self.assertFalse((base / "records/installed-skill__scoped-implementation.json").exists())
            self.assertIn("selected 2 of the fixed three", (base / "report.md").read_text())
            duplicate_args = args.copy()
            duplicate_args[duplicate_args.index("unconfirmed-observation")] = "missing-scope"
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as captured:
                cli.main(duplicate_args)
            self.assertEqual(captured.exception.code, 2)

    def test_real_fixture_preparation_and_mechanical_grading_boundaries(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            checkout, state = base / "project", base / "state"
            fixture = smoke.prepare_fixture(ROOT, checkout, state, "scoped-implementation")
            self.assertTrue((checkout / smoke.SKILL).is_file())
            self.assertTrue(fixture["installed_files_sha256"])
            self.assertNotIn(smoke.RULE, (checkout / "README.md").read_text())
            self.assertIn(smoke.RULE, (checkout / "docs/memory/constraints.md").read_text())
            self.assertEqual(fixture["protocol_version"], "0.8")
            source = checkout / "src/account.py"
            correct = smoke.SOURCE.replace("return str(value)", "return 'acct:' + str(value).zfill(4)")
            source.write_text(correct, encoding="utf-8")
            mutation = event({"type": "file_change", "id": "write"}, "item.started")
            complete = smoke.grade(checkout, state, fixture, runtime(proof(read_event(), mutation)))
            self.assertEqual(complete["status"], "PASS", complete)
            late = smoke.grade(checkout, state, fixture, runtime(proof(mutation, read_event())))
            self.assertEqual(late["status"], "FAIL")
            unobserved = smoke.grade(checkout, state, fixture, runtime(proof(read_event())))
            self.assertEqual(unobserved["status"], "REVIEW")
            source.write_text(smoke.SOURCE, encoding="utf-8")
            missing = dict(fixture, task_id="missing-scope")
            refused = smoke.grade(checkout, state, missing, runtime(proof(read_event(route="INCOMPLETE"))))
            self.assertEqual(refused["status"], "PASS", refused)
            candidate_fixture = dict(fixture, task_id="unconfirmed-observation")
            candidate_payload = smoke.installed_cli(checkout, state, "add", "Retries might improve throughput.", "--type", "decision",
                                                    "--candidate", "--evidence", "agent-observed")
            candidate_write = event({"type": "command_execution", "id": "add",
                                     "command": smoke.CLI + " add --candidate"}, "item.started")
            candidate_done = event({"type": "command_execution", "id": "add", "command": smoke.CLI + " add --candidate",
                                    "aggregated_output": json.dumps(candidate_payload), "exit_code": 0})
            candidate = smoke.grade(checkout, state, candidate_fixture,
                                    runtime(proof(read_event(task="maintenance"), candidate_write, candidate_done)))
            self.assertEqual(candidate["status"], "PASS", candidate)
            (checkout / smoke.INSTALL / "scripts/memory-custodian").write_text("changed", encoding="utf-8")
            changed = smoke.grade(checkout, state, candidate_fixture, runtime(proof(read_event(task="maintenance"))))
            self.assertEqual(changed["status"], "BLOCKER")

    def test_controller_keeps_stub_records_offline_and_writes_exclusively(self):
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            args = ["--codex-executable", sys.executable, "--model-version", "test-model",
                    "--record-dir", str(base / "records"), "--report-file", str(base / "report.md")]
            runtime_values = [dict(runtime(proof()), thread_id="offline-" + str(index)) for index in range(3)]
            with patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "codex-cli test-stub", "")), patch.object(
                cli, "prepare_fixture", side_effect=lambda root, checkout, state, task: {"task_id": task}
            ), patch.object(cli, "run_runtime", side_effect=runtime_values), patch.object(cli, "grade", return_value={"status": "PASS"}), redirect_stdout(io.StringIO()):
                status = cli.main(args)
            self.assertEqual(status, 2)
            records = [json.loads(path.read_text()) for path in (base / "records").glob("installed-skill__*.json")]
            self.assertEqual(len(records), 3)
            self.assertTrue(all(row["evidence_class"] == "offline-runtime-stub" and row["status"] == "BLOCKER" for row in records))
            for line in (base / "records/SHA256SUMS").read_text().splitlines():
                digest, filename = line.split("  ", 1)
                self.assertEqual(smoke.sha((base / "records" / filename).read_bytes()), digest)
            destination = base / "exclusive.json"
            cli.write_new(destination, {"line": "one\ntwo"})
            before = destination.read_bytes()
            self.assertTrue(before.endswith(b"\n"))
            self.assertNotIn(b"\r\n", before)
            with self.assertRaises(FileExistsError):
                cli.write_new(destination, {"overwrite": True})
            self.assertEqual(destination.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
