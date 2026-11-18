"""Development-only, paired interruption experiment; not a checkpoint product.

The existing 0.13 adapter and evidence hashes remain unchanged. Runtime JSONL
is consumed in memory; only allowlisted observable metadata is retained.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time

from benchmarks.runners.codex_runtime import _relative_change_path, _stop_process
from benchmarks.runners.harness import (
    command_for, copy_tree, grade_checkout, iter_files, prepare_checkout, tree_hash,
)
from benchmarks.graders.mechanical import run_visible_tests


TASKS = ("field-ledger-split-export", "field-ledger-rounding", "route-notes-redact-secrets")
CONDITIONS = ("FRESH", "OBSERVABLE_CHECKPOINT", "NATIVE_RESUME")
PREFIX = (
    "Work independently in this checkout. Use only its files and the supplied "
    "task context; native continuation may use this same session's history. "
    "Follow repository instructions. Make the requested changes and verify "
    "them. Do not access other workspaces or external services, commit, or "
    "publish. Do not invent project facts.\n\nTask:\n"
)
POLICY = "workspace-write;network=off;approval=never;config/skills/plugins/memories/delegation=off;reasoning=low"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Observations:
    """Never retain reasoning items, command arguments, or raw tool output."""

    def __init__(self, checkout: Path):
        self.checkout = checkout
        self.thread_id = None
        self.completed = 0
        self.failed = False
        self.invalid = False
        self.tools = set()
        self.completed_tools = []
        self.completed_ids = set()
        self.messages = []
        self.usage = {}

    def accept(self, event: object) -> None:
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            self.invalid = True
            return
        kind = event["type"]
        if self.completed:
            self.invalid = True
        if kind == "thread.started":
            value = event.get("thread_id")
            if self.thread_id is not None or not isinstance(value, str) or not value:
                self.invalid = True
            else:
                self.thread_id = value
        elif self.thread_id is None:
            self.invalid = True
        if kind in {"error", "turn.failed"}:
            self.failed = True
        elif kind == "turn.completed":
            self.completed += 1
            usage = event.get("usage")
            if isinstance(usage, dict):
                for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
                    value = usage.get(key)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        self.usage[key] = value
        elif kind in {"item.started", "item.completed"}:
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                self.invalid = True
                return
            item_type = item.get("type")
            if not isinstance(item_type, str):
                self.invalid = True
                return
            if item_type in {"command_execution", "file_change", "mcp_tool_call", "web_search"}:
                self.tools.add(item["id"])
            if kind != "item.completed":
                return
            if item_type in {"command_execution", "file_change"}:
                if item["id"] in self.completed_ids:
                    return
                self.completed_ids.add(item["id"])
                row = {"type": item_type, "id": item["id"]}
                code = item.get("exit_code")
                if isinstance(code, int) and not isinstance(code, bool):
                    row["exit_code"] = code
                changes = []
                for change in item.get("changes", []) if isinstance(item.get("changes"), list) else []:
                    if isinstance(change, dict):
                        path = _relative_change_path(change.get("path"), self.checkout)
                        if path:
                            changes.append(path)
                if changes:
                    row["changed_paths"] = changes
                self.completed_tools.append(row)
            elif item_type == "agent_message" and isinstance(item.get("text"), str):
                # Public progress only, from synthetic fixtures. Reasoning events
                # and tool responses never become checkpoint content.
                message = item["text"].replace(str(self.checkout), "<checkout>")
                self.messages.append(message[:1200])

    def summary(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "completion_events": self.completed,
            "event_contract_valid": bool(self.thread_id) and not self.invalid and not self.failed,
            "tool_calls": len(self.tools),
            "completed_tools": self.completed_tools,
            "total_input_tokens": self.usage.get("input_tokens"),
            "total_output_tokens": self.usage.get("output_tokens"),
            "cached_input_tokens": self.usage.get("cached_input_tokens"),
            "repeated_file_reads": None,
        }


def argv(executable: str, model: str, checkout: Path, *, resume: str | None = None,
         persistent: bool = False) -> list[str]:
    command = [executable, "exec", "--ignore-user-config", "--json",
               "--sandbox", "workspace-write", "--skip-git-repo-check", "--model", model,
               "-c", 'approval_policy="never"',
               "-c", "sandbox_workspace_write.network_access=false",
               "-c", 'model_reasoning_effort="low"', "-c", 'web_search="disabled"',
               "-c", "features.skip_host_skill_discovery=true", "-c", "skills.bundled.enabled=false"]
    for name in ("apps", "plugins", "remote_plugin", "memories", "multi_agent", "shell_snapshot"):
        command.extend(["--disable", name])
    command.extend(["-C", str(checkout.resolve())])
    if resume:
        command.extend(["resume", resume, "-"])
    else:
        if not persistent:
            command.append("--ephemeral")
        command.append("-")
    return command


def stream_run(command: list[str], checkout: Path, prompt: str, *, timeout: int,
               interrupt_after: int | None = None) -> tuple[dict, list[str]]:
    """Stop the process group at the selected completed-tool event boundary."""
    started = time.monotonic()
    observations = Observations(checkout)
    result = {"status": "BLOCKER", "detail": "runtime unavailable",
              "prompt_sha256": sha(prompt.encode()), "raw_trace_retained": False}
    stdout_hash, stderr_hash = hashlib.sha256(), hashlib.sha256()
    buffer = b""
    interrupted = False
    timed_out = False
    alive_at_signal = False
    process = None
    try:
        process = subprocess.Popen(command, cwd=checkout, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        process.stdin.write(prompt.encode())
        process.stdin.close()
        process.stdin = None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                if time.monotonic() - started > timeout:
                    result["detail"] = "runtime timeout"
                    timed_out = True
                    break
                for key, _ in selector.select(timeout=0.1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stderr":
                        stderr_hash.update(chunk)
                        continue
                    stdout_hash.update(chunk)
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            observations.accept(json.loads(line))
                        except (ValueError, UnicodeDecodeError):
                            observations.invalid = True
                        if (interrupt_after is not None
                                and len(observations.completed_tools) >= interrupt_after
                                and observations.completed == 0):
                            interrupted = True
                            break
                    if interrupted:
                        break
                if interrupted:
                    alive_at_signal = process.poll() is None
                    result["detail"] = "forced process-group interruption at completed-tool boundary"
                    break
            if interrupted or timed_out:
                _stop_process(process)
            else:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    result["detail"] = "runtime did not exit after closing its event stream"
                    _stop_process(process)
        if buffer.strip() and not interrupted:
            observations.invalid = True
        summary = observations.summary()
        signal_exit = process.returncode is not None and process.returncode < 0
        if interrupted and summary["event_contract_valid"] and alive_at_signal and signal_exit:
            result["status"] = "INTERRUPTED"
        elif interrupted:
            result.update(status="INVALID", detail="tool boundary reached without a verified live process-group termination")
        elif not timed_out and process.returncode == 0 and summary["event_contract_valid"] and observations.completed == 1:
            result.update(status="COMPLETED", detail="one successful runtime turn")
        elif result["detail"] == "runtime unavailable":
            result["detail"] = "runtime failed or incomplete event contract"
    except (OSError, ValueError):
        result["detail"] = "runtime launch or stream failed"
    finally:
        if process is not None:
            if process.poll() is None:
                _stop_process(process)
            for handle in (process.stdout, process.stderr):
                if handle is not None:
                    handle.close()
    result.update(observations.summary())
    result.update(wall_clock_seconds=round(time.monotonic() - started, 6),
                  event_stream_sha256=stdout_hash.hexdigest(), stderr_sha256=stderr_hash.hexdigest(),
                  exit_code=process.returncode if process is not None else None)
    if interrupt_after is not None:
        result["interruption"] = {"boundary_completed_tools": interrupt_after,
                                  "alive_at_signal": alive_at_signal,
                                  "signal_exit_observed": interrupted and result["exit_code"] is not None and result["exit_code"] < 0}
    return result, observations.messages[-3:]


def file_fingerprints(checkout: Path) -> dict[str, str]:
    return {path.relative_to(checkout).as_posix(): sha(path.read_bytes())
            for path in iter_files(checkout, ())}


def checkpoint_summary(prefix: dict, messages: list[str], before: dict, after: dict) -> dict:
    return {
        "experimental_observable_summary_version": 1,
        "authority": "advisory execution metadata; verify against current files",
        "completed_tools": prefix["completed_tools"],
        "public_progress": messages,
        "changed_files": {path: digest for path, digest in after.items() if before.get(path) != digest},
        "deleted_files": sorted(set(before) - set(after)),
        "next_step": "Continue the original task from the current files and verify it with tests.",
        "unobserved": ["hidden reasoning", "raw command arguments", "raw tool output", "repeated file reads"],
    }


def evaluate(root: Path, task: dict, checkout: Path) -> dict:
    visible = run_visible_tests(checkout, command_for(task))
    oracle = grade_checkout(root, task, checkout)
    oracle_status = oracle.get("status")
    if visible not in {"PASS", "FAIL"} or oracle_status not in {"PASS", "FAIL"}:
        status = "BLOCKER"
    else:
        status = "PASS" if visible == oracle_status == "PASS" else "FAIL"
    return {"status": status,
            "visible_tests": visible, "oracle_status": oracle.get("status"),
            "failure_labels": oracle.get("failure_labels", [])}


def run_pair(root: Path, task: dict, work: Path, *, executable: str, model: str,
             repetition: int, order_offset: int, timeout: int) -> dict:
    checkout, snapshot = work / "checkout", work / "snapshot"
    prepare_checkout(root, task, "MEMORYCUSTODIAN", checkout)
    before = file_fingerprints(checkout)
    initial_tree_hash = tree_hash(checkout)
    initial_memory = {name: digest for name, digest in before.items() if name.startswith("docs/memory/")}
    prompt = PREFIX + task["task_prompt"]
    prefix, messages = stream_run(argv(executable, model, checkout, persistent=True),
                                  checkout, prompt, timeout=timeout, interrupt_after=2)
    row = {"task_id": task["task_id"], "task_version": task["task_version"],
           "repetition": repetition, "prefix": prefix, "conditions": [],
           "task_sha256": sha(json.dumps(task, sort_keys=True).encode()),
           "declared_fixture_sha256": task["repo"]["commit"],
           "initial_visible_tree_sha256": initial_tree_hash,
           "prefix_prompt_sha256": sha(prompt.encode())}
    if prefix["status"] != "INTERRUPTED":
        row.update(status="BLOCKER" if prefix["status"] == "BLOCKER" else "INAPPLICABLE",
                   detail="prefix did not reach the prescribed interruption boundary")
        return row
    row["interrupted_tree_sha256"] = tree_hash(checkout)
    after = file_fingerprints(checkout)
    if {name: digest for name, digest in after.items() if name.startswith("docs/memory/")} != initial_memory:
        row.update(status="BLOCKER", detail="prefix mutated authoritative fixture memory")
        return row
    summary = checkpoint_summary(prefix, messages, before, after)
    row["checkpoint"] = summary
    # Grade a copy so oracle/test execution cannot change the paired snapshot.
    copy_tree(checkout, snapshot, ())
    probe = work / "prefix-grading"
    copy_tree(snapshot, probe, ())
    row["prefix_grade"] = evaluate(root, task, probe)
    if row["prefix_grade"]["status"] == "BLOCKER":
        row.update(status="BLOCKER", detail="prefix grading unavailable")
        return row
    if row["prefix_grade"]["status"] == "PASS":
        row.update(status="INAPPLICABLE", detail="task already solved at interruption")
        return row
    order = list(CONDITIONS[order_offset % 3:] + CONDITIONS[:order_offset % 3])
    for condition in order:
        shutil.rmtree(checkout)
        copy_tree(snapshot, checkout, ())
        before_hash = tree_hash(checkout)
        if before_hash != row["interrupted_tree_sha256"]:
            raise ValueError("paired snapshot changed")
        continuation = PREFIX + task["task_prompt"] + (
            "\n\nExecution was interrupted. Continue from the current files. "
            "Prior tool processes have been stopped; do not assume an earlier command completed."
        )
        if condition == "OBSERVABLE_CHECKPOINT":
            continuation += "\n\nObservable progress summary (advisory):\n" + json.dumps(summary, sort_keys=True)
        resume = prefix["thread_id"] if condition == "NATIVE_RESUME" else None
        runtime, _ = stream_run(argv(executable, model, checkout, resume=resume),
                                checkout, continuation, timeout=timeout)
        runtime["token_usage_scope"] = "recovery session"
        if resume:
            # This CLI reports session-cumulative usage on resume. An interrupted
            # turn supplies no completed usage baseline, so subtraction would
            # invent post-resume measurements.
            runtime["token_usage_scope"] = "session cumulative; post-resume baseline unavailable"
            for key in ("total_input_tokens", "total_output_tokens", "cached_input_tokens"):
                runtime["runtime_reported_" + key] = runtime.get(key)
                runtime[key] = None
        cell = {"condition": condition, "starting_tree_sha256": before_hash, "runtime": runtime}
        current_memory = {name: digest for name, digest in file_fingerprints(checkout).items()
                          if name.startswith("docs/memory/")}
        cell["fixture_memory_unchanged"] = current_memory == initial_memory
        if runtime["status"] != "COMPLETED":
            cell["status"] = "BLOCKER"
        elif current_memory != initial_memory:
            cell.update(status="BLOCKER", detail="runtime mutated authoritative fixture memory")
        elif resume and runtime["thread_id"] != resume:
            cell.update(status="BLOCKER", detail="native resume did not preserve session identity")
        else:
            cell.update(evaluate(root, task, checkout))
        row["conditions"].append(cell)
    row["status"] = "COMPLETE" if all(cell["status"] != "BLOCKER" for cell in row["conditions"]) else "BLOCKER"
    return row
