#!/usr/bin/env python3
"""Batch Benchmark Runner and Aggregator for MemoryCustodian.

Runs a matrix of tasks x conditions using `scripts/run-memory-bench.py`
and produces aggregated statistics, paired comparison metrics,
and detailed Markdown/JSON reports.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.runners.harness import HarnessError, load_tasks, make_result_id
from benchmarks.runners.codex_runtime import TOOL_POLICY as CODEX_TOOL_POLICY


CONDITIONS = (
    "NO_MEMORY",
    "PLATFORM_FILE_ONLY",
    "EQUIVALENT_MANUAL_DOCS",
    "MEMORYCUSTODIAN",
)


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def load_task_list(root: Path, suite: str = "core") -> list[str]:
    return [task["task_id"] for task in load_tasks(root) if task.get("suite") == suite]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch benchmarks across conditions and aggregate results.")
    parser.add_argument("--suite", default="core", help="Benchmark suite (default: core)")
    parser.add_argument(
        "--tasks",
        default="all",
        help="Comma-separated task IDs or 'all' (default: all)",
    )
    parser.add_argument(
        "--conditions",
        default=",".join(CONDITIONS),
        help=f"Comma-separated conditions (default: {','.join(CONDITIONS)})",
    )
    parser.add_argument("--runtime", default="headless-agent", help="Runtime name label")
    parser.add_argument("--mode", choices=("command", "live"), default="command")
    parser.add_argument("--codex-executable", help="Explicit native Codex executable for live mode")
    parser.add_argument(
        "--agent-cmd",
        help="Command string used by the runner to invoke the agent in each checkout",
    )
    parser.add_argument("--record-dir", help="Directory where individual result records are persisted (append-only)")
    parser.add_argument("--repetition-id", default="1", help="Repetition ID (default: 1)")
    parser.add_argument("--timeout", type=int, default=60, help="Per-task subprocess timeout in seconds (default: 60)")
    parser.add_argument("--jobs", type=int, default=1, help="Maximum concurrent isolated runs (default: 1)")
    parser.add_argument("--model-version", default="", help="Model version label")
    parser.add_argument("--tool-policy", default="", help="Tool policy label")
    parser.add_argument("--resume", action="store_true", help="Skip runs whose result record already exists in --record-dir")
    parser.add_argument("--condition-order", choices=("balanced", "fixed"), default="balanced",
                        help="Rotate condition order by task index, or preserve the supplied order")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and exit without running")
    parser.add_argument("--report-file", help="Path to write the aggregated markdown report")
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "table"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    return parser.parse_args(argv)


def get_existing_records(record_dir: Path) -> dict[str, dict]:
    if not record_dir.is_dir():
        return {}
    existing = {}
    for path in sorted(record_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read existing result: {path.name}") from exc
        if not isinstance(data, dict) or data.get("result_id") != path.stem:
            raise ValueError(f"existing result identity does not match filename: {path.name}")
        existing[path.stem] = data
    return existing


def execution_plan(task_ids: list[str], conditions: list[str], order: str) -> list[tuple[str, str]]:
    plan = []
    for index, task_id in enumerate(task_ids):
        offset = index % len(conditions) if order == "balanced" else 0
        for condition in conditions[offset:] + conditions[:offset]:
            plan.append((task_id, condition))
    return plan


def validate_record(record: dict, task: dict, condition: str, args: argparse.Namespace) -> None:
    expected = {
        "result_id": make_result_id(task, condition, args.runtime, args.repetition_id, task["repo"]["commit"]),
        "suite": task["suite"], "task_id": task["task_id"], "task_version": task["task_version"],
        "condition": condition, "runtime": args.runtime, "repetition_id": args.repetition_id,
        "fixture_sha256": task["repo"]["commit"], "model_version": args.model_version or None,
        "tool_policy": args.tool_policy or (CODEX_TOOL_POLICY if args.mode == "live" else "command-adapter"),
    }
    for field, value in expected.items():
        if record.get(field) != value:
            raise ValueError(f"result {expected['result_id']} has mismatched {field}; use a new repetition or record directory")
    if record.get("status") not in {"PASS", "FAIL", "BLOCKER", "REVIEW"}:
        raise ValueError(f"result {expected['result_id']} has an invalid status")
    evidence = "live-runtime" if args.mode == "live" else "command-adapter"
    allowed_evidence = {evidence}
    if args.mode == "live" and record.get("status") == "BLOCKER":
        allowed_evidence.add("live-runtime-unavailable")
    if record.get("evidence_class") not in allowed_evidence:
        raise ValueError(f"result {expected['result_id']} has mismatched evidence_class")


def run_single_task(
    root: Path,
    task_id: str,
    condition: str,
    runtime: str,
    agent_cmd: str,
    repetition_id: str,
    timeout: int,
    record_dir: Path | None,
    model_version: str,
    tool_policy: str,
    mode: str = "command",
    codex_executable: str | None = None,
) -> dict | None:
    runner_script = root / "scripts" / "run-memory-bench.py"
    cmd = [
        sys.executable,
        str(runner_script),
        "--mode",
        mode,
        "--runtime",
        runtime,
        "--condition",
        condition,
        "--task",
        task_id,
        "--repetition-id",
        repetition_id,
        "--timeout",
        str(timeout),
    ]
    if agent_cmd:
        cmd.extend(["--agent-cmd", agent_cmd])
    if codex_executable:
        cmd.extend(["--codex-executable", codex_executable])
    if record_dir:
        cmd.extend(["--record-dir", str(record_dir)])
    if model_version:
        cmd.extend(["--model-version", model_version])
    if tool_policy:
        cmd.extend(["--tool-policy", tool_policy])

    res = subprocess.run(
        cmd,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if res.stdout:
        try:
            records = json.loads(res.stdout)
            if res.returncode in (0, 2) and isinstance(records, list) and len(records) == 1 and isinstance(records[0], dict):
                return records[0]
        except json.JSONDecodeError:
            pass

    return {
        "task_id": task_id,
        "condition": condition,
        "runtime": runtime,
        "repetition_id": repetition_id,
        "status": "BLOCKER",
        "detail": res.stderr.strip() or f"process exit {res.returncode}",
        "failure_labels": ["COMMAND_FAILED"],
        "memory_label": None,
        "metrics": {"task_success": False},
    }


def aggregate_results(
    task_ids: list[str],
    conditions: list[str],
    records: list[dict],
) -> dict:
    matrix: dict[str, dict[str, dict]] = {t: {} for t in task_ids}
    by_condition: dict[str, dict[str, int]] = {c: {"total": 0, "pass": 0, "fail": 0, "blocker": 0, "review": 0} for c in conditions}
    label_counts: dict[str, dict[str, int]] = {c: {} for c in conditions}

    for record in records:
        t = record.get("task_id")
        c = record.get("condition")
        st = record.get("status", "BLOCKER")
        if t not in matrix or c not in by_condition:
            raise ValueError("result is outside the requested task/condition matrix")
        if c in matrix[t]:
            raise ValueError(f"duplicate result for {t} [{c}]")
        if st not in {"PASS", "FAIL", "BLOCKER", "REVIEW"}:
            raise ValueError(f"invalid result status for {t} [{c}]")
        matrix[t][c] = record

        if c in by_condition:
            by_condition[c]["total"] += 1
            if st == "PASS":
                by_condition[c]["pass"] += 1
            elif st == "FAIL":
                by_condition[c]["fail"] += 1
            elif st == "BLOCKER":
                by_condition[c]["blocker"] += 1
            elif st == "REVIEW":
                by_condition[c]["review"] += 1

            for label in record.get("failure_labels", []):
                label_counts[c][label] = label_counts[c].get(label, 0) + 1

    # Paired comparison between EQUIVALENT_MANUAL_DOCS and MEMORYCUSTODIAN
    paired = {
        "total_pairs": 0,
        "both_pass": 0,
        "both_fail": 0,
        "mc_only_pass": 0,
        "manual_only_pass": 0,
        "neither_run": 0,
        "incomplete_pairs": 0,
        "success_rate_difference": None,
        "bootstrap_95_interval": None,
        "uncertainty_method": "paired task bootstrap, 10000 resamples, seed 0; descriptive pilot only",
    }
    differences = []
    if "EQUIVALENT_MANUAL_DOCS" in conditions and "MEMORYCUSTODIAN" in conditions:
        for t in task_ids:
            man = matrix[t].get("EQUIVALENT_MANUAL_DOCS", {}).get("status")
            mc = matrix[t].get("MEMORYCUSTODIAN", {}).get("status")
            if man in {"PASS", "FAIL"} and mc in {"PASS", "FAIL"}:
                paired["total_pairs"] += 1
                differences.append(int(mc == "PASS") - int(man == "PASS"))
                if man == "PASS" and mc == "PASS":
                    paired["both_pass"] += 1
                elif man != "PASS" and mc != "PASS":
                    paired["both_fail"] += 1
                elif mc == "PASS" and man != "PASS":
                    paired["mc_only_pass"] += 1
                elif man == "PASS" and mc != "PASS":
                    paired["manual_only_pass"] += 1
            else:
                paired["incomplete_pairs"] += 1
                if not man and not mc:
                    paired["neither_run"] += 1
    if differences:
        count = len(differences)
        paired["success_rate_difference"] = sum(differences) / count
        rng = random.Random(0)
        samples = sorted(sum(rng.choices(differences, k=count)) / count for _ in range(10000))
        paired["bootstrap_95_interval"] = [samples[249], samples[9749]]

    return {
        "matrix": matrix,
        "by_condition": by_condition,
        "label_counts": label_counts,
        "paired": paired,
    }


def format_markdown_report(
    summary: dict,
    task_ids: list[str],
    conditions: list[str],
    runtime: str,
    model_version: str,
) -> str:
    lines = [
        "# Memory Benchmark Evaluation Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Runtime: `{runtime}`",
        f"- Model version: `{model_version or 'unspecified'}`",
        f"- Tasks evaluated: {len(task_ids)}",
        f"- Conditions: {', '.join(f'`{c}`' for c in conditions)}",
        "- Evidence boundary: pilot-development results are descriptive; no comparative effectiveness claim.",
        "",
        "## 1. Condition Summary",
        "",
        "| Condition | Total | PASS | FAIL | BLOCKER | REVIEW | Success Rate |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for c in conditions:
        st = summary["by_condition"][c]
        tot = st["total"]
        passed = st["pass"]
        pct = (passed / tot * 100) if tot > 0 else 0.0
        lines.append(
            f"| `{c}` | {tot} | {passed} | {st['fail']} | {st['blocker']} | {st['review']} | {pct:.1f}% |"
        )

    lines.extend([
        "",
        "## 2. Primary Paired Comparison (EQUIVALENT_MANUAL_DOCS vs MEMORYCUSTODIAN)",
        "",
    ])
    p = summary["paired"]
    if p["total_pairs"] > 0:
        lines.extend([
            f"- **Total paired tasks**: {p['total_pairs']}",
            f"- **Both PASS**: {p['both_pass']} ({p['both_pass'] / p['total_pairs'] * 100:.1f}%)",
            f"- **Both FAIL**: {p['both_fail']} ({p['both_fail'] / p['total_pairs'] * 100:.1f}%)",
            f"- **MEMORYCUSTODIAN only PASS**: {p['mc_only_pass']}",
            f"- **EQUIVALENT_MANUAL_DOCS only PASS**: {p['manual_only_pass']}",
            f"- **Incomplete pairs excluded**: {p['incomplete_pairs']} (missing, BLOCKER, or REVIEW)",
            f"- **Paired success-rate difference (MC − manual)**: {p['success_rate_difference'] * 100:.1f} percentage points",
            f"- **95% paired bootstrap interval**: [{p['bootstrap_95_interval'][0] * 100:.1f}, {p['bootstrap_95_interval'][1] * 100:.1f}] percentage points",
            f"- Uncertainty method: {p['uncertainty_method']}.",
            "- This resamples the observed tasks, not new repositories or independent runtime repetitions. Small, related fixture tasks and one repetition cannot establish a general benefit.",
        ])
    else:
        lines.append(f"*No complete, gradeable pairs; {p['incomplete_pairs']} pairs excluded.*")

    lines.extend([
        "",
        "## 3. Failure Label Distribution",
        "",
        "| Condition | Failure Labels |",
        "| :--- | :--- |",
    ])
    for c in conditions:
        lbls = summary["label_counts"][c]
        if lbls:
            lbl_str = ", ".join(f"`{k}`: {v}" for k, v in sorted(lbls.items()))
        else:
            lbl_str = "None"
        lines.append(f"| `{c}` | {lbl_str} |")

    lines.extend([
        "",
        "## 4. Task Outcome Matrix",
        "",
        "| Task ID | " + " | ".join(f"`{c}`" for c in conditions) + " |",
        "| :--- | " + " | ".join(":---:" for _ in conditions) + " |",
    ])
    for t in task_ids:
        row = [f"`{t}`"]
        for c in conditions:
            cell = summary["matrix"][t].get(c)
            if not cell:
                row.append("-")
            else:
                status = cell.get("status", "UNKNOWN")
                labels = cell.get("failure_labels", [])
                if status == "PASS":
                    row.append("✅ PASS")
                elif status == "FAIL":
                    detail = labels[0] if labels else "FAIL"
                    row.append(f"❌ {detail}")
                else:
                    row.append(f"⚠️ {status}")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root_from_here()

    if args.timeout <= 0 or args.jobs <= 0:
        print("timeout and jobs must be positive", file=sys.stderr)
        return 1
    if args.mode == "command" and not args.agent_cmd:
        print("command mode requires --agent-cmd", file=sys.stderr)
        return 1
    if args.mode == "live" and (args.runtime != "codex" or not args.codex_executable or not args.model_version):
        print("native live mode requires --runtime codex, --codex-executable, and --model-version", file=sys.stderr)
        return 1
    if args.mode == "live" and args.agent_cmd:
        print("native live mode cannot use --agent-cmd", file=sys.stderr)
        return 1
    if args.resume and not args.record_dir:
        print("--resume requires --record-dir", file=sys.stderr)
        return 1
    try:
        tasks = [task for task in load_tasks(root) if task.get("suite") == args.suite]
    except HarnessError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    all_tasks = [task["task_id"] for task in tasks]
    task_by_id = {task["task_id"]: task for task in tasks}
    if args.tasks == "all":
        selected_tasks = all_tasks
    else:
        requested = [t.strip() for t in args.tasks.split(",") if t.strip()]
        selected_tasks = [t for t in all_tasks if t in requested]
        missing = set(requested) - set(selected_tasks)
        if missing:
            print(f"unknown tasks: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1

    selected_conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    invalid_conds = [c for c in selected_conditions if c not in CONDITIONS]
    if invalid_conds:
        print(f"invalid conditions: {', '.join(invalid_conds)}", file=sys.stderr)
        return 1
    if not selected_tasks or not selected_conditions:
        print("at least one task and condition are required", file=sys.stderr)
        return 1
    if len(set(selected_conditions)) != len(selected_conditions):
        print("duplicate conditions are not allowed", file=sys.stderr)
        return 1
    if args.tasks != "all" and len(set(requested)) != len(requested):
        print("duplicate tasks are not allowed", file=sys.stderr)
        return 1

    record_dir = Path(args.record_dir).resolve() if args.record_dir else None
    progress = sys.stderr if args.format == "json" else sys.stdout
    total_runs = len(selected_tasks) * len(selected_conditions)
    print(f"MemoryCustodian Batch Benchmark: {len(selected_tasks)} tasks x {len(selected_conditions)} conditions = {total_runs} runs.", file=progress)
    plan = execution_plan(selected_tasks, selected_conditions, args.condition_order)

    if args.dry_run:
        print("Dry run requested. Planned execution matrix:", file=progress)
        for t in selected_tasks:
            order = [c for task_id, c in plan if task_id == t]
            print(f"- {t}: {', '.join(order)}", file=progress)
        if args.format == "json":
            print(json.dumps({"plan": plan, "condition_order": args.condition_order, "jobs": args.jobs}))
        return 0

    try:
        existing = get_existing_records(record_dir) if record_dir else {}
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    records = []
    pending = []
    # Preflight the complete matrix before launching any new runtime.
    try:
        for run_idx, (task_id, condition) in enumerate(plan, 1):
            task = task_by_id[task_id]
            result_id = make_result_id(task, condition, args.runtime, args.repetition_id, task["repo"]["commit"])
            if result_id in existing:
                if not args.resume:
                    raise ValueError(f"result already exists: {result_id}; use --resume or a new repetition")
                record = existing[result_id]
                validate_record(record, task, condition, args)
                records.append(record)
                print(f"[{run_idx}/{total_runs}] Resume: {task_id} [{condition}] {record['status']}", file=progress)
            else:
                pending.append((run_idx, task_id, condition))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    def run(item: tuple[int, str, str]) -> dict:
        _, task_id, condition = item
        return run_single_task(root, task_id, condition, args.runtime, args.agent_cmd,
                               args.repetition_id, args.timeout, record_dir, args.model_version,
                               args.tool_policy, args.mode, args.codex_executable)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for item in pending:
            print(f"[{item[0]}/{total_runs}] Queued: {item[1]} [{item[2]}]", file=progress, flush=True)
        for item, record in zip(pending, pool.map(run, pending)):
            run_idx, task_id, condition = item
            if record.get("result_id"):
                try:
                    validate_record(record, task_by_id[task_id], condition, args)
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    return 1
            records.append(record)
            labels = ", ".join(record.get("failure_labels", []))
            print(f"[{run_idx}/{total_runs}] {task_id} [{condition}]: {record['status']} {labels}", file=progress, flush=True)

    summary = aggregate_results(selected_tasks, selected_conditions, records)
    summary["execution"] = {"condition_order": args.condition_order, "jobs": args.jobs,
                            "repetition_id": args.repetition_id, "planned_runs": total_runs}

    if args.format == "json":
        output = json.dumps(summary, indent=2)
    else:
        output = format_markdown_report(
            summary,
            selected_tasks,
            selected_conditions,
            args.runtime,
            args.model_version,
        )

    print("\n" + output)

    if args.report_file:
        rf = Path(args.report_file)
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text(output + "\n", encoding="utf-8")
        print(f"\nReport written to: {rf}", file=progress)

    return 2 if any(record["status"] in {"BLOCKER", "REVIEW"} for record in records) else 0


if __name__ == "__main__":
    sys.exit(main())
