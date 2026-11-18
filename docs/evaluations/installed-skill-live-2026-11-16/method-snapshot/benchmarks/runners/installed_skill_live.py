"""Explicit installed-Skill invocation smoke; independent of frozen pilots.

No raw runtime payloads are retained. Unit stubs use a distinct evidence class.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from benchmarks.runners.codex_runtime import _stop_process, summarize_events


TASK_IDS = ("scoped-implementation", "missing-scope", "unconfirmed-observation")
INSTALL = Path(".installed/memory-custodian")
SKILL = ".agents/skills/memory-custodian/SKILL.md"
CLI = ".installed/memory-custodian/scripts/memory-custodian"
ENTRY_POINTS = (CLI, ".installed/memory-custodian/bin/memory-custodian")
POLICY = (
    "workspace-write;agent-shell-network=off;approval=never;ephemeral;user-config=ignored;"
    "host-skills/bundled-skills/apps/plugins/memories/web/delegation=off;manual-project-skill-invocation;reasoning=low"
)
RULE = (
    "Account labels use the prefix acct: followed by the nonnegative integer in base ten, "
    "padded to at least four digits with leading zeroes. Keep the existing ValueError input validation."
)
SOURCE = (
    "def account_label(value):\n"
    "    if not isinstance(value, int) or isinstance(value, bool) or value < 0:\n"
    "        raise ValueError('expected a nonnegative integer')\n"
    "    return str(value)\n"
)
TASKS = {
    "scoped-implementation": "Implement account_label in src/account.py according to the project's account-label rule. Preserve existing input validation and verify the change. Only src/account.py may be edited; keep the installed distribution and existing active memory unchanged. Propose any additional memory update in your final reply instead of writing it.",
    "missing-scope": "Perform admission for an implementation task using exactly the caller's supplied routing scope: no paths and no areas. Do not add inferred scope for this admission check. Report whether implementation may proceed in your final reply without editing any project files.",
    "unconfirmed-observation": "Record this one observation in project memory using the appropriate confidence: retries might improve throughput. This is an agent observation; neither the user nor an authoritative project source has confirmed it. Only docs/memory/inbox.md may be edited, with exactly one candidate for this observation. Do not create active memory or modify source code; propose any other update in your final reply.",
}
INSTRUCTIONS = (
    "This task explicitly invokes the project-local installed memory-custodian Skill. "
    f"Read {SKILL}, then follow it using {CLI}. "
    "Use only this checkout and supplied task context. Do not inspect other workspaces, "
    "global configuration, credentials, or the runtime's private state. The bundled CLI "
    "may use its isolated private state internally. Do not commit, publish, or use external "
    "services. Invoke strict routing with --format json in a separate tool call before "
    "any source or memory mutation. Do not combine a routing command and a write in one "
    "tool call. Preserve the complete CLI JSON envelope in tool output without piping, "
    "filtering, or truncating it. Treat routing inputs and evidence according to the installed Skill.\n\nTask:\n"
)
METHODS = (
    "benchmarks/runners/installed_skill_live.py", "scripts/run-installed-skill-eval.py",
    "docs/evaluations/INSTALLED-SKILL-LIVE-PLAN-2026-11-16.md",
    "benchmarks/runners/codex_runtime.py",
)


class SmokeError(RuntimeError):
    pass


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprints(root: Path) -> dict[str, str]:
    result = {}
    for directory, folders, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        folders[:] = [name for name in folders if name != "__pycache__"]
        for name in list(folders) + names:
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                target = os.readlink(path)
                if relative != ".agents/skills/memory-custodian" or Path(target).is_absolute():
                    raise SmokeError("unexpected fixture symlink")
                if not path.resolve().is_relative_to(root.resolve()):
                    raise SmokeError("fixture symlink escapes checkout")
                result[relative] = sha(("symlink:" + target).encode())
            elif path.is_file() and path.suffix not in (".pyc", ".pyo"):
                result[relative] = sha(path.read_bytes())
    return result


def tree_digest(values: dict[str, str]) -> str:
    return sha("\n".join(f"{name}\t{values[name]}" for name in sorted(values)).encode())


def environment(state: Path) -> dict[str, str]:
    value = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "MEMORY_CUSTODIAN_FAILPOINT"):
        value.pop(name, None)
    value.update(XDG_STATE_HOME=str(state), PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE="1")
    return value


def installed_cli(checkout: Path, state: Path, *arguments: str) -> dict:
    result = subprocess.run(
        [str(checkout / CLI), *arguments, "--project-root", str(checkout), "--format", "json"],
        cwd=checkout, env=environment(state), capture_output=True, text=True, timeout=30, check=False,
    )
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise SmokeError("installed CLI did not return JSON") from exc
    if result.returncode or value.get("output_schema_version") != 1 or value.get("status") == "FAIL":
        raise SmokeError("installed CLI fixture preparation or verification failed")
    return value


def prepare_fixture(root: Path, checkout: Path, state: Path, task_id: str) -> dict:
    if task_id not in TASK_IDS:
        raise SmokeError("unknown installed-Skill smoke task")
    checkout.mkdir(parents=True)
    state.mkdir(parents=True, mode=0o700)
    distribution = checkout / INSTALL
    for relative in ("cli", "skills", "bin", "scripts/memory-custodian"):
        source, target = root / relative, distribution / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            raise SmokeError("source distribution is a symlink")
        if source.is_dir():
            if any(path.is_symlink() for path in source.rglob("*")):
                raise SmokeError("source distribution contains a symlink")
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        else:
            shutil.copy2(source, target)
    skill_link = checkout / ".agents/skills/memory-custodian"
    skill_link.parent.mkdir(parents=True)
    skill_link.symlink_to("../../.installed/memory-custodian/skills/memory-custodian", target_is_directory=True)
    (checkout / "README.md").write_text("# Account fixture\n\nA local account-label component.\n", encoding="utf-8")
    (checkout / "src").mkdir()
    (checkout / "src/account.py").write_text(SOURCE, encoding="utf-8")
    initialized = installed_cli(checkout, state, "init", "--agent", "codex")
    memory = checkout / "docs/memory"
    (memory / "brief.md").write_text(
        "# Project Brief\n\nPurpose:\nA local account-label component.\n\n"
        "Current direction:\nFollow scoped project memory for implementation and maintenance.\n", encoding="utf-8",
    )
    with (checkout / "AGENTS.md").open("a", encoding="utf-8") as handle:
        handle.write("\n## Installed Skill invocation\n\n" + INSTRUCTIONS.split("\n\nTask:")[0] + "\n")
    subject_args = ("subject", "add", "Account labels", "--kind", "feature", "--evidence", "user-confirmed")
    preview = installed_cli(checkout, state, *subject_args)
    installed_cli(checkout, state, *subject_args, "--apply", "--confirm-plan", preview["data"]["plan"]["plan_id"])
    subject_id = re.search(r"(?m)^## (MC-SUBJ-\d{8}-[0-9a-f]{8}) — Account labels$", (memory / "subjects.md").read_text()).group(1)
    installed_cli(checkout, state, "add", RULE, "--type", "constraint", "--subject", subject_id,
                  "--facet", "interface", "--evidence", "user-confirmed")
    installed_cli(checkout, state, "enable", "area/accounts", "--path", "src/**")
    initial = fingerprints(checkout)
    version = subprocess.run([str(checkout / CLI), "--version"], cwd=checkout,
                             env=environment(state), capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    return {"task_id": task_id, "package_version": version, "protocol_version": initialized["protocol_version"],
            "initial_files": initial, "fixture_sha256": tree_digest(initial),
            "installed_files_sha256": {name: value for name, value in initial.items() if name.startswith(INSTALL.as_posix() + "/")},
            "skill_sha256": sha((checkout / SKILL).read_bytes()), "prompt_sha256": sha((INSTRUCTIONS + TASKS[task_id]).encode()),
            "task_sha256": sha(TASKS[task_id].encode())}


def runtime_argv(executable: str, model: str, checkout: Path, state: Path) -> list[str]:
    command = [executable, "exec", "--ignore-user-config", "--ephemeral", "--json",
               "--sandbox", "workspace-write", "--skip-git-repo-check", "--model", model,
               "--add-dir", str(state.resolve()), "-c", 'approval_policy="never"',
               "-c", "sandbox_workspace_write.network_access=false", "-c", 'model_reasoning_effort="low"',
               "-c", 'web_search="disabled"', "-c", "features.skip_host_skill_discovery=true",
               "-c", "skills.bundled.enabled=false"]
    for feature in ("apps", "plugins", "remote_plugin", "memories", "multi_agent", "shell_snapshot"):
        command.extend(["--disable", feature])
    command.extend(["-C", str(checkout.resolve()), "-"])
    return command


def _cli_documents(text: str) -> list[dict]:
    values = []
    for line in text.splitlines():
        try:
            payload = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if (isinstance(payload, dict) and type(payload.get("output_schema_version")) is int
                and payload["output_schema_version"] == 1
                and payload.get("protocol_version") == "0.8" and isinstance(payload.get("data"), dict)):
            values.append(payload)
    return values


def observe(stdout: str) -> dict:
    """Classify observable events; raw values are never returned."""
    metadata, strict_reads, skill_reads, mutations = [], [], [], []
    external = False
    for sequence, line in enumerate(stdout.splitlines(), 1):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue  # summarize_events rejects malformed event streams.
        if not isinstance(event, dict) or event.get("type") not in ("item.started", "item.completed"):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind not in ("command_execution", "file_change", "agent_message", "web_search", "mcp_tool_call"):
            continue
        row = {"sequence": sequence, "event": event["type"], "type": kind}
        if kind in ("web_search", "mcp_tool_call"):
            external = True
        command = item.get("command", "")
        output = item.get("aggregated_output", "")
        if not isinstance(command, str):
            command = ""
        if not isinstance(output, str):
            output = ""
        for key in ("command", "aggregated_output", "text"):
            value = item.get(key)
            if isinstance(value, str):
                row[key + "_sha256"] = sha(value.encode())
        code = item.get("exit_code")
        if isinstance(code, int) and not isinstance(code, bool):
            row["exit_code"] = code
        if event["type"] == "item.started":
            shell_write = bool(re.search(r"write_text|write_bytes|apply_patch|\btee\b|\bsed\s+-i|\bcp\b|\bmv\b|>\s*[^&]", command))
            memory_write = any(entry in command for entry in ENTRY_POINTS) and bool(re.search(r"\b(add|promote|forget|compact|init|enable|migrate)\b", command))
            if kind == "file_change" or shell_write or memory_write:
                mutations.append(sequence)
                row["possible_mutation"] = True
        if event["type"] == "item.completed" and kind == "command_execution":
            if (SKILL in command or ".installed/memory-custodian/skills/memory-custodian/SKILL.md" in command) and code == 0:
                if "name: memory-custodian" in output and "## Hard Gate" in output:
                    skill_reads.append(sequence)
                    row["installed_skill_content_observed"] = True
            if any(entry in command for entry in ENTRY_POINTS) and "--strict-routing" in command and re.search(r"\bread\b", command):
                for value in _cli_documents(output):
                    data = value["data"]
                    route = data.get("routing_completeness")
                    successful = type(code) is int and route == "COMPLETE" and value.get("status") == "PASS" and value.get("exit_class") == "success" and code == 0
                    rejected = type(code) is int and route in ("INCOMPLETE", "INVALID", "AMBIGUOUS") and value.get("status") == "FAIL" and value.get("exit_class") in ("domain-failure", "blocker") and code in (1, 2)
                    if value.get("command") == "read" and (successful or rejected):
                        proof = {"sequence": sequence, "status": value.get("status"),
                                 "exit_class": value.get("exit_class"), "routing": data["routing_completeness"],
                                 "canonical_task": data.get("canonical_task"),
                                 "expected_source_path": data.get("normalized_paths") == ["src/account.py"]}
                        strict_reads.append(proof)
                        row["installed_cli_strict_read"] = proof
        metadata.append(row)
    return {"events": metadata, "strict_reads": strict_reads, "skill_read_sequences": skill_reads,
            "mutation_sequences": mutations, "forbidden_external_tool": external}


def run_runtime(command: list[str], checkout: Path, state: Path, prompt: str, *, timeout: int,
                evidence_class: str = "offline-runtime-stub") -> dict:
    if evidence_class not in {"offline-runtime-stub", "live-runtime"}:
        raise SmokeError("invalid runtime evidence class")
    started = time.monotonic()
    result = {"status": "BLOCKER", "evidence_class": evidence_class, "raw_trace_retained": False,
              "detail": "runtime unavailable"}
    process = None
    try:
        process = subprocess.Popen(command, cwd=checkout, env=environment(state), text=True,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=os.name == "posix")
        try:
            stdout, stderr = process.communicate(input=prompt, timeout=timeout)
        except (subprocess.TimeoutExpired, UnicodeError):
            _stop_process(process)
            result["detail"] = "runtime timed out or returned invalid encoding"
            return result
        summary = summarize_events(stdout, checkout=checkout)
        result.update({name: summary.get(name) for name in (
            "thread_id", "completion_events", "event_count", "tool_calls", "total_input_tokens", "total_output_tokens",
        )})
        result.update(observations=observe(stdout), event_stream_sha256=sha(stdout.encode()),
                      stderr_sha256=sha(stderr.encode()), exit_code=process.returncode)
        if process.returncode == 0 and summary.get("valid"):
            result.update(status="COMPLETED", detail="one verified single-turn event stream")
        else:
            result["detail"] = "runtime did not complete one valid successful turn"
    except OSError:
        result["detail"] = "runtime launch failed"
    finally:
        if process is not None and process.poll() is None:
            _stop_process(process)
        result["wall_clock_seconds"] = round(time.monotonic() - started, 6)
    return result


def grade(checkout: Path, state: Path, fixture: dict, runtime: dict) -> dict:
    if runtime.get("status") != "COMPLETED":
        return {"status": "BLOCKER", "checks": {"runtime_completed": False}}
    after = fingerprints(checkout)
    before = fixture["initial_files"]
    changes = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    if any(name.startswith(INSTALL.as_posix() + "/") or name == ".agents/skills/memory-custodian" for name in changes):
        return {"status": "BLOCKER", "checks": {"installed_sources_unchanged": False}}
    observations = runtime["observations"]
    task = fixture["task_id"]
    required_task = "maintenance" if task == "unconfirmed-observation" else "implementation"
    required_route = "INCOMPLETE" if task == "missing-scope" else "COMPLETE"
    reads = [value for value in observations["strict_reads"] if value["canonical_task"] == required_task
             and value["routing"] == required_route
             and value["status"] == ("FAIL" if required_route == "INCOMPLETE" else "PASS")
             and (task != "scoped-implementation" or value["expected_source_path"])]
    checks = {"runtime_completed": True, "installed_sources_unchanged": True,
              "skill_content_observed": bool(observations["skill_read_sequences"]),
              "required_strict_read_observed": bool(reads),
              "no_external_tools": not observations["forbidden_external_tool"]}
    if task == "missing-scope":
        checks["no_artifact_changes"] = not changes
    elif task == "scoped-implementation":
        checks["only_requested_code_changed"] = changes == {"src/account.py"}
        program = (
            "import importlib.util,sys;sys.dont_write_bytecode=True;"
            "s=importlib.util.spec_from_file_location('account','src/account.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "assert all(m.account_label(n)=='acct:'+str(n).zfill(4) for n in (0,7,42,9999,10000));"
            "exec(\"for n in (-1,1.5,True,None):\\n try: m.account_label(n)\\n except ValueError: pass\\n else: raise AssertionError('invalid accepted')\")"
        )
        try:
            result = subprocess.run([sys.executable, "-I", "-c", program], cwd=checkout,
                                    env=environment(state), capture_output=True, timeout=20, check=False)
            checks["account_behavior"] = result.returncode == 0
        except subprocess.TimeoutExpired:
            checks["account_behavior"] = False
    else:
        checks["only_inbox_changed"] = changes == {"docs/memory/inbox.md"}
        try:
            listed = installed_cli(checkout, state, "list", "--status", "candidate")
        except SmokeError:
            listed = {"data": {}}
        inbox = (checkout / "docs/memory/inbox.md").read_text(encoding="utf-8")
        entries = listed["data"].get("entries", [])
        checks["exactly_one_candidate"] = len(entries) == 1 and entries[0].get("source") == "docs/memory/inbox.md"
        checks["unconfirmed_evidence"] = "- agent-observed" in inbox or "- conversation-unconfirmed" in inbox
        checks["observation_retained"] = "retr" in inbox.casefold() and "throughput" in inbox.casefold()
        checks["no_active_inbox_entry"] = "Status: active" not in inbox
    if task != "missing-scope":
        mutations = observations["mutation_sequences"]
        if changes and not mutations:
            return {"status": "REVIEW", "checks": checks, "detail": "artifact changed without an observable mutation boundary"}
        checks["strict_read_before_mutation"] = bool(reads) and bool(mutations) and min(value["sequence"] for value in reads) < min(mutations)
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def make_record(fixture: dict, runtime: dict, outcome: dict, provenance: dict) -> dict:
    evidence = runtime.get("evidence_class", "offline-runtime-stub")
    # Defaults remain offline: unit stubs cannot silently turn into live evidence.
    return {"installed_skill_record_format": 1, "result_id": "installed-skill__" + fixture["task_id"],
            "task_id": fixture["task_id"], "status": outcome["status"], "evidence_class": evidence,
            "invocation_mode": "explicit installed Skill-file and bundled-CLI invocation; automatic discovery untested",
            "fixture": fixture, "runtime": runtime, "outcome": outcome, "provenance": provenance}
