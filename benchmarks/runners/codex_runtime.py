"""Opt-in, real Codex CLI runtime for the development pilot.

Only normalized event metadata is returned. Raw responses, commands, and
stderr are never written to the public result records.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import signal
import subprocess
import time


TOOL_POLICY = (
    "codex-workspace-write;network=off;approval=never;user-config=ignored;"
    "ephemeral;reasoning=low;host-skills=off;plugins=off;memories=off"
)
PROMPT_PREFIX = (
    "Work independently in the current repository checkout. Use only the files "
    "inside this checkout and the task below. Do not access other workspaces, "
    "parent directories, external services, or prior task sessions. Follow any "
    "repository instructions present. Make the requested changes directly in "
    "this checkout, and verify them with the available tests. Do not invent "
    "project facts that are absent. Do not commit or publish anything.\n\nTask:\n"
)
_TOOLS = {"command_execution", "file_change", "mcp_tool_call", "web_search"}


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _relative_change_path(value: object, checkout: Path | None) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    path = Path(value)
    if path.is_absolute():
        if checkout is None:
            return None
        try:
            value = path.resolve().relative_to(checkout.resolve()).as_posix()
        except (OSError, ValueError):
            return None
    if "\\" in value or PureWindowsPath(value).drive:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        return None
    return relative.as_posix()


def _trace_item(kind: str, item: dict, checkout: Path | None) -> dict | None:
    item_type = item.get("type")
    if item_type not in _TOOLS | {"agent_message"}:
        return None
    trace = {"event": kind, "type": item_type, "id": item["id"]}
    status = item.get("status")
    if isinstance(status, str) and status in {"in_progress", "completed", "failed", "pending", "declined"}:
        trace["status"] = status
    exit_code = item.get("exit_code")
    if isinstance(exit_code, int) and not isinstance(exit_code, bool):
        trace["exit_code"] = exit_code
    for name in ("text", "aggregated_output"):
        value = item.get(name)
        if isinstance(value, str):
            trace[f"{name}_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()
    command = item.get("command")
    if isinstance(command, str):
        mentions = set(re.findall(r"(?<![A-Za-z0-9_-])docs/(?:memory|manual)(?:/[A-Za-z0-9_.-]+)*", command))
        paths = sorted(path for path in mentions if _relative_change_path(path, None))
        if paths:
            trace["source_path_mentions"] = paths
    changes = item.get("changes")
    if isinstance(changes, list):
        normalized = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            path = _relative_change_path(change.get("path"), checkout)
            if path is not None:
                change_kind = change.get("kind")
                normalized.append({
                    "path": path,
                    "kind": change_kind if isinstance(change_kind, str) and change_kind in {"add", "update", "delete"} else "unknown",
                })
        if normalized:
            trace["changes"] = normalized
    return trace


def summarize_events(stdout: str, *, checkout: Path | None = None) -> dict:
    """Require a complete JSONL turn, retaining only observable quantities."""
    thread_id = None
    completed = 0
    failed = False
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    cached_known = True
    usage_known = True
    tools = set()
    event_count = 0
    action_trace = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return {"valid": False, "reason": "invalid JSONL event"}
        if not isinstance(event, dict):
            return {"valid": False, "reason": "invalid event object"}
        event_count += 1
        kind = event.get("type")
        if not isinstance(kind, str) or not kind:
            return {"valid": False, "reason": "invalid event type"}
        if completed:
            return {"valid": False, "reason": "event after turn completion"}
        if kind == "thread.started":
            if thread_id is not None or not isinstance(event.get("thread_id"), str) or not event["thread_id"].strip():
                return {"valid": False, "reason": "invalid session identity"}
            thread_id = event["thread_id"]
        elif thread_id is None:
            return {"valid": False, "reason": "event before session identity"}
        elif kind in {"turn.failed", "error"}:
            failed = True
        elif kind == "turn.completed":
            completed += 1
            usage = event.get("usage")
            if not isinstance(usage, dict) or not all(
                _nonnegative_int(usage.get(key)) for key in ("input_tokens", "output_tokens")
            ):
                usage_known = False
            else:
                input_tokens += usage["input_tokens"]
                output_tokens += usage["output_tokens"]
                cached = usage.get("cached_input_tokens")
                if _nonnegative_int(cached) and cached <= usage["input_tokens"]:
                    cached_tokens += cached
                else:
                    cached_known = False
        elif kind in {"item.started", "item.completed"}:
            item = event.get("item", {})
            if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not isinstance(item.get("id"), str) or not item["id"].strip():
                return {"valid": False, "reason": "invalid item event"}
            if item.get("type") in _TOOLS:
                tools.add(item["id"])
            trace = _trace_item(kind, item, checkout)
            if trace is not None:
                action_trace.append(trace)
    valid = thread_id is not None and completed == 1 and not failed
    return {
        "valid": valid,
        "reason": "completed real Codex turn" if valid else "no successful single-turn completion",
        "thread_id": thread_id,
        "completion_events": completed,
        "event_count": event_count,
        "tool_calls": len(tools),
        "total_input_tokens": input_tokens if usage_known and completed else None,
        "total_output_tokens": output_tokens if usage_known and completed else None,
        "cached_input_tokens": cached_tokens if usage_known and cached_known and completed else None,
        "action_trace": action_trace,
    }


def _stop_process(process: subprocess.Popen) -> None:
    """Stop the whole runtime group so a timed-out agent cannot keep writing."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        try:
            process.communicate(timeout=2)
        except UnicodeDecodeError:
            process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        try:
            process.communicate()
        except UnicodeDecodeError:
            process.wait()


def run_codex(
    checkout: Path,
    prompt: str,
    *,
    executable: str,
    model: str,
    timeout: int,
) -> dict:
    """Execute one fresh session; errors remain blockers, never synthetic runs."""
    started = time.monotonic()
    result = {"status": "blocked", "detail": "Codex runtime unavailable", "metrics": {}, "runtime_metadata": {}}
    resolved = shutil.which(executable)
    if not resolved or not model or timeout <= 0:
        result["detail"] = "Codex executable, pinned model, and positive timeout are required"
        return result
    try:
        version_result = subprocess.run(
            [resolved, "--version"], text=True, capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        result["detail"] = "Codex version probe failed"
        return result
    version = version_result.stdout.strip()
    if version_result.returncode or not version.startswith("codex-cli "):
        result["detail"] = "executable did not identify itself as Codex CLI"
        return result
    effective_prompt = PROMPT_PREFIX + prompt
    command = [
        resolved, "exec", "--ignore-user-config", "--ephemeral", "--json",
        "--sandbox", "workspace-write", "--skip-git-repo-check", "--model", model,
        "-c", 'approval_policy="never"',
        "-c", "sandbox_workspace_write.network_access=false",
        "-c", 'model_reasoning_effort="low"',
        "-c", 'web_search="disabled"',
        "-c", "features.skip_host_skill_discovery=true",
        "-c", "skills.bundled.enabled=false",
        "--disable", "apps", "--disable", "plugins", "--disable", "remote_plugin",
        "--disable", "memories", "--disable", "multi_agent", "--disable", "shell_snapshot",
        "-C", str(checkout.resolve()), "-",
    ]
    metadata = {
        "adapter": "codex-exec-jsonl-v1",
        "cli_version": version,
        "requested_model": model,
        "tool_policy": TOOL_POLICY,
        "effective_prompt_sha256": hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest(),
        "prompt_prefix_sha256": hashlib.sha256(PROMPT_PREFIX.encode("utf-8")).hexdigest(),
        "raw_trace_retained": False,
    }
    result["runtime_metadata"] = metadata
    try:
        process = subprocess.Popen(
            command, cwd=checkout, text=True, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name == "posix",
        )
        try:
            stdout, stderr = process.communicate(input=effective_prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            result["detail"] = f"Codex runtime timed out after {timeout}s"
            result["metrics"]["wall_clock_seconds"] = round(time.monotonic() - started, 6)
            return result
        except UnicodeDecodeError:
            _stop_process(process)
            result["detail"] = "Codex runtime returned invalid text encoding"
            result["metrics"]["wall_clock_seconds"] = round(time.monotonic() - started, 6)
            return result
    except OSError:
        result["detail"] = "Codex runtime could not be launched"
        return result
    summary = summarize_events(stdout, checkout=checkout)
    metadata.update({key: value for key, value in summary.items() if key not in {"valid", "reason"}})
    metadata["event_stream_sha256"] = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    metadata["stderr_sha256"] = hashlib.sha256(stderr.encode("utf-8")).hexdigest()
    metadata["exit_code"] = process.returncode
    result["metrics"] = {
        "wall_clock_seconds": round(time.monotonic() - started, 6),
        **{key: summary.get(key) for key in ("total_input_tokens", "total_output_tokens", "tool_calls")},
    }
    if process.returncode != 0 or not summary["valid"]:
        result["detail"] = f"Codex runtime did not complete (exit {process.returncode}; {summary['reason']})"
        return result
    result["status"] = "completed"
    result["detail"] = "Real Codex CLI completed one isolated pilot session"
    return result
