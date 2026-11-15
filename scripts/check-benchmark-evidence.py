#!/usr/bin/env python3
"""Validate normalized evidence for the fixed 2026-11-13 development pilot.

This is a static consistency check. It never launches an agent or grader,
does not authenticate event hashes, and cannot regrade discarded checkouts.
PASS consistency relies on the recorded, hashed harness's oracle gate.
Historical method hashes need only agree unless --check-current-source is set.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.runners.harness import (
    CONDITIONS, FAILURE_LABELS, HarnessError, fixture_pin_issues,
    isolation_issues, load_tasks, make_result_id, parity_issues,
    prepare_checkout, tree_hash,
)


MODEL = "gpt-6.1-sol"
REPETITION = "pilot-20261113"
BUDGET = {"time_seconds": 180, "token_limit": None}
POLICY = (
    "codex-workspace-write;network=off;approval=never;user-config=ignored;"
    "ephemeral;reasoning=low;host-skills=off;plugins=off;memories=off"
)
# Keep the historical neutral prefix here; later runtime changes must not
# invalidate this fixed pilot unless current-source verification is requested.
PREFIX = (
    "Work independently in the current repository checkout. Use only the files "
    "inside this checkout and the task below. Do not access other workspaces, "
    "parent directories, external services, or prior task sessions. Follow any "
    "repository instructions present. Make the requested changes directly in "
    "this checkout, and verify them with the available tests. Do not invent "
    "project facts that are absent. Do not commit or publish anything.\n\nTask:\n"
)
SOURCE_PATHS = (
    "benchmarks/graders/mechanical.py", "benchmarks/runners/codex_runtime.py",
    "benchmarks/runners/harness.py", "scripts/run-batch-benchmark.py",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
METRIC_BOOLEANS = (
    "task_success", "hard_constraint_violation", "memory_dependent_requirement_satisfied",
    "stale_memory_used", "unsupported_memory_used", "tests_run",
)
UNOBSERVED = ("routing_complete", "context_memory_tokens", "repeated_file_reads")
TOOL_TYPES = {"command_execution", "file_change", "mcp_tool_call", "web_search"}
TRACE_FIELDS = {
    "event", "type", "id", "status", "exit_code", "text_sha256", "aggregated_output_sha256",
    "source_path_mentions", "changes",
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _hash(value: object) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _relative(value: object) -> bool:
    return (isinstance(value, str) and bool(value) and "\\" not in value and "\x00" not in value
            and not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).drive
            and all(part not in {"", ".", ".."} for part in value.split("/")))


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def load_records(directory: Path) -> list[dict]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("record directory must be a real directory")
    records = []
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"record must be a regular file: {path.name}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                                parse_constant=_reject_constant)
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"malformed record: {path.name}: {exc}") from exc
        if not isinstance(record, dict) or record.get("result_id") != path.stem:
            raise ValueError(f"record identity does not match filename: {path.name}")
        records.append(record)
    return records


def expected_inputs(root: Path) -> tuple[list[dict], dict[tuple[str, str], str]]:
    tasks = [task for task in load_tasks(root) if task.get("suite") == "core"]
    if len(tasks) != 18 or {task.get("split") for task in tasks} != {"pilot-development"}:
        raise ValueError("the fixed pilot requires 18 core pilot-development tasks")
    if any(task.get("task_version") != 1 for task in tasks):
        raise ValueError("the fixed pilot requires task version 1")
    issues = fixture_pin_issues(root, tasks)
    if issues:
        raise ValueError("; ".join(issues))
    hashes = {}
    # Only copy/hash visible text. No runtime, generated code, oracle, or test is executed.
    with tempfile.TemporaryDirectory(prefix="memory-custodian-evidence-") as name:
        for index, task in enumerate(tasks):
            for condition in CONDITIONS:
                checkout = Path(name) / f"{index}-{condition}"
                prepare_checkout(root, task, condition, checkout)
                issues = isolation_issues(checkout, condition) + parity_issues(task, condition, checkout)
                if issues:
                    raise ValueError("; ".join(issues))
                hashes[(task["task_id"], condition)] = tree_hash(checkout)
    return tasks, hashes


def validate_records(root: Path, records: list[dict], tasks: list[dict], inputs: dict,
                     *, check_current_source: bool = False) -> list[str]:
    issues = []
    task_map = {task["task_id"]: task for task in tasks}
    expected_cells = {(task_id, condition) for task_id in task_map for condition in CONDITIONS}
    cells = set()
    result_ids = set()
    sessions = set()
    method = None
    environment = None
    current = None
    if check_current_source:
        current = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in SOURCE_PATHS}
    if len(records) != len(expected_cells):
        issues.append(f"expected {len(expected_cells)} records, found {len(records)}")
    for index, record in enumerate(records):
        label = f"record {index + 1}"
        if not isinstance(record, dict):
            issues.append(f"{label}: expected an object")
            continue
        task_id, condition = record.get("task_id"), record.get("condition")
        if not isinstance(task_id, str) or not isinstance(condition, str):
            issues.append(f"{label}: invalid task or condition")
            continue
        cell = (task_id, condition)
        label = f"{task_id} [{condition}]"
        if cell not in expected_cells:
            issues.append(f"{label}: outside the fixed pilot matrix")
            continue
        if cell in cells:
            issues.append(f"{label}: duplicate task/condition cell")
        cells.add(cell)
        task = task_map[task_id]
        expected_id = make_result_id(task, condition, "codex", REPETITION, task["repo"]["commit"])
        expected = {
            "result_format": "1", "result_id": expected_id, "suite": "core",
            "task_version": task["task_version"], "runtime": "codex", "evidence_class": "live-runtime",
            "model_version": MODEL, "tool_policy": POLICY, "repetition_id": REPETITION,
            "package_version": "0.13.0", "protocol_version": "0.8", "budget": BUDGET,
            "fixture_sha256": task["repo"]["commit"], "prompt_sha256": digest(task["task_prompt"]),
            "visible_source_sha256": inputs[cell], "checkout_id": inputs[cell],
        }
        for key, value in expected.items():
            if record.get(key) != value or type(record.get(key)) is not type(value):
                issues.append(f"{label}: mismatched {key}")
        result_id = record.get("result_id")
        if isinstance(result_id, str):
            if result_id in result_ids:
                issues.append(f"{label}: duplicate result ID")
            result_ids.add(result_id)
        status = record.get("status")
        if not isinstance(status, str) or status not in {"PASS", "FAIL"}:
            issues.append(f"{label}: incomplete pilot outcome {status!r}")
        sources = record.get("runner_source_sha256")
        if not isinstance(sources, dict) or set(sources) != set(SOURCE_PATHS) or not all(_hash(value) for value in sources.values()):
            issues.append(f"{label}: malformed method source hashes")
        else:
            if method is None:
                method = sources
            elif sources != method:
                issues.append(f"{label}: method source hashes changed within the pilot")
            if current is not None and sources != current:
                issues.append(f"{label}: method source hashes differ from current source")
        commit = record.get("git_commit")
        if not isinstance(commit, str) or not HEX40.fullmatch(commit) or not isinstance(record.get("git_dirty"), bool):
            issues.append(f"{label}: invalid Git provenance")
        os_name = record.get("os")
        if not isinstance(os_name, str) or not os_name.strip():
            issues.append(f"{label}: missing OS provenance")
        meta = record.get("runtime_metadata")
        if not isinstance(meta, dict):
            issues.append(f"{label}: missing runtime metadata")
            continue
        expected_meta = {
            "adapter": "codex-exec-jsonl-v1", "requested_model": MODEL, "tool_policy": POLICY,
            "completion_events": 1, "exit_code": 0, "raw_trace_retained": False,
            "prompt_prefix_sha256": digest(PREFIX),
            "effective_prompt_sha256": digest(PREFIX + task["task_prompt"]),
        }
        for key, value in expected_meta.items():
            if meta.get(key) != value or isinstance(meta.get(key), bool) != isinstance(value, bool):
                issues.append(f"{label}: mismatched runtime {key}")
        version = meta.get("cli_version")
        if not isinstance(version, str) or not version.startswith("codex-cli "):
            issues.append(f"{label}: invalid actual CLI version")
        settings = (commit, os_name, version, record.get("git_dirty"))
        if environment is None:
            environment = settings
        elif settings != environment:
            issues.append(f"{label}: runtime environment changed within the pilot")
        session = meta.get("thread_id")
        if not isinstance(session, str) or not session.strip():
            issues.append(f"{label}: missing independent session ID")
        elif session in sessions:
            issues.append(f"{label}: reused session ID")
        else:
            sessions.add(session)
        for key in ("event_stream_sha256", "stderr_sha256"):
            if not _hash(meta.get(key)):
                issues.append(f"{label}: invalid runtime {key}")
        if not _integer(meta.get("event_count")) or meta["event_count"] < 2:
            issues.append(f"{label}: invalid runtime event count")
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            issues.append(f"{label}: missing metrics")
            continue
        for key in METRIC_BOOLEANS:
            if not isinstance(metrics.get(key), bool):
                issues.append(f"{label}: invalid metric {key}")
        for key in UNOBSERVED:
            if key not in metrics or metrics[key] is not None:
                issues.append(f"{label}: unobserved {key} must be null")
        for key in ("total_input_tokens", "total_output_tokens", "tool_calls"):
            if not _integer(metrics.get(key)) or not _integer(meta.get(key)) or metrics.get(key) != meta.get(key):
                issues.append(f"{label}: invalid or mismatched observed {key}")
        cached = meta.get("cached_input_tokens")
        if cached is not None and (not _integer(cached) or not _integer(meta.get("total_input_tokens")) or cached > meta["total_input_tokens"]):
            issues.append(f"{label}: invalid cached input tokens")
        elapsed = metrics.get("wall_clock_seconds")
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            issues.append(f"{label}: invalid observed duration")
        labels = record.get("failure_labels")
        if not isinstance(labels, list) or any(not isinstance(value, str) or value not in FAILURE_LABELS for value in labels):
            issues.append(f"{label}: invalid failure labels")
            labels = []
        if metrics.get("task_success") is not (status == "PASS"):
            issues.append(f"{label}: task outcome and success metric disagree")
        if metrics.get("tests_run") is not True or not isinstance(metrics.get("final_test_status"), str) or metrics.get("final_test_status") not in {"PASS", "FAIL"}:
            issues.append(f"{label}: missing visible test outcome")
        if status == "PASS" and (metrics.get("final_test_status") != "PASS" or labels or record.get("memory_label") != "MEMORY_NONE" or metrics.get("memory_dependent_requirement_satisfied") is not True):
            issues.append(f"{label}: PASS does not satisfy the recorded oracle/visible-test gate")
        for key, failure in (("hard_constraint_violation", "MEMORY_AUTHORITY_VIOLATION"),
                             ("stale_memory_used", "MEMORY_STALE_USE"),
                             ("unsupported_memory_used", "MEMORY_FALSE_POSITIVE")):
            if metrics.get(key) is not (failure in labels):
                issues.append(f"{label}: {key} disagrees with oracle labels")
        trace = meta.get("action_trace")
        if not isinstance(trace, list):
            issues.append(f"{label}: missing normalized action trace")
            continue
        tools = set()
        for item in trace:
            if not isinstance(item, dict) or set(item) - TRACE_FIELDS:
                issues.append(f"{label}: malformed or raw action trace")
                continue
            if not isinstance(item.get("event"), str) or item.get("event") not in {"item.started", "item.completed"} or not isinstance(item.get("type"), str) or item.get("type") not in TOOL_TYPES | {"agent_message"} or not isinstance(item.get("id"), str) or not item["id"]:
                issues.append(f"{label}: invalid normalized action event")
                continue
            if item["type"] in TOOL_TYPES:
                tools.add(item["id"])
            for key in ("text_sha256", "aggregated_output_sha256"):
                if key in item and not _hash(item[key]):
                    issues.append(f"{label}: invalid normalized action hash")
            mentions = item.get("source_path_mentions", [])
            if not isinstance(mentions, list) or any(not _relative(path) or not (path in {"docs/manual", "docs/memory"} or path.startswith(("docs/manual/", "docs/memory/"))) for path in mentions):
                issues.append(f"{label}: invalid source path mentions")
            changes = item.get("changes", [])
            if not isinstance(changes, list) or any(not isinstance(change, dict) or not _relative(change.get("path")) for change in changes):
                issues.append(f"{label}: invalid normalized changed paths")
        if len(tools) != metrics.get("tool_calls"):
            issues.append(f"{label}: trace tool count disagrees with observed usage")
    missing = expected_cells - cells
    if missing:
        issues.append(f"missing {len(missing)} task/condition cells")
    return issues


def check_report(root: Path, report_path: Path, records: list[dict], tasks: list[dict]) -> list[str]:
    """Reproduce semantic report rows while allowing dated prose/appendices."""
    path = root / "scripts" / "run-batch-benchmark.py"
    spec = importlib.util.spec_from_file_location("memory_benchmark_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task_ids = [task["task_id"] for task in tasks]
    summary = module.aggregate_results(task_ids, list(CONDITIONS), records)
    expected = module.format_markdown_report(summary, task_ids, list(CONDITIONS), "codex", MODEL)
    try:
        actual = report_path.read_text(encoding="utf-8")
    except OSError:
        return ["report file is missing or unreadable"]
    rows = [line for line in expected.splitlines() if line.startswith("|") or line.startswith("- **")]
    return ["report rows do not reproduce normalized records"] if any(row not in actual.splitlines() for row in rows) else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-dir", type=Path, default=ROOT / "docs/evaluations/benchmark/runs/pilot-2026-11-13")
    parser.add_argument("--report-file", type=Path, help="Also reproduce and check the report's result rows")
    parser.add_argument("--check-current-source", action="store_true", help="Require recorded method hashes to match current files")
    args = parser.parse_args(argv)
    try:
        tasks, inputs = expected_inputs(ROOT)
        records = load_records(args.record_dir)
        issues = validate_records(ROOT, records, tasks, inputs, check_current_source=args.check_current_source)
        if not issues and args.report_file:
            issues.extend(check_report(ROOT, args.report_file, records, tasks))
    except (OSError, ValueError, HarnessError) as exc:
        issues = [str(exc)]
    if issues:
        print("MemoryCustodian pilot evidence: FAIL")
        for issue in issues:
            print(f"- {issue}")
        return 1
    counts = Counter(record["status"] for record in records)
    print("MemoryCustodian pilot evidence: OK")
    print(f"Records: {len(records)}; independent sessions: {len(records)}; PASS: {counts['PASS']}; FAIL: {counts['FAIL']}")
    print("Static normalized-evidence consistency only; no agent or grader was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
