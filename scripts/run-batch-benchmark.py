#!/usr/bin/env python3
"""Batch Benchmark Runner and Aggregator for MemoryCustodian.

Runs a matrix of tasks x conditions using `scripts/run-memory-bench.py`
and produces aggregated statistics, paired comparison metrics,
and detailed Markdown/JSON reports.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


CONDITIONS = (
    "NO_MEMORY",
    "PLATFORM_FILE_ONLY",
    "EQUIVALENT_MANUAL_DOCS",
    "MEMORYCUSTODIAN",
)


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def load_task_list(root: Path, suite: str = "core") -> list[str]:
    tasks_dir = root / "benchmarks" / "tasks"
    task_ids = []
    for path in sorted(tasks_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("suite") == suite:
                task_ids.append(data.get("task_id"))
        except Exception:
            continue
    return task_ids


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
    parser.add_argument(
        "--agent-cmd",
        required=True,
        help="Command string used by the runner to invoke the agent in each checkout",
    )
    parser.add_argument("--record-dir", help="Directory where individual result records are persisted (append-only)")
    parser.add_argument("--repetition-id", default="1", help="Repetition ID (default: 1)")
    parser.add_argument("--timeout", type=int, default=60, help="Per-task subprocess timeout in seconds (default: 60)")
    parser.add_argument("--model-version", default="", help="Model version label")
    parser.add_argument("--tool-policy", default="", help="Tool policy label")
    parser.add_argument("--resume", action="store_true", help="Skip runs whose result record already exists in --record-dir")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and exit without running")
    parser.add_argument("--report-file", help="Path to write the aggregated markdown report")
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "table"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    return parser.parse_args(argv)


def get_existing_result_ids(record_dir: Path) -> set[str]:
    if not record_dir.is_dir():
        return set()
    existing = set()
    for path in record_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "result_id" in data:
                existing.add(data["result_id"])
        except Exception:
            continue
    return existing


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
) -> dict | None:
    runner_script = root / "scripts" / "run-memory-bench.py"
    cmd = [
        sys.executable,
        str(runner_script),
        "--mode",
        "command",
        "--runtime",
        runtime,
        "--condition",
        condition,
        "--task",
        task_id,
        "--agent-cmd",
        agent_cmd,
        "--repetition-id",
        repetition_id,
        "--timeout",
        str(timeout),
    ]
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
            if isinstance(records, list) and records:
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
        if t in matrix and c in matrix[t]:
            pass
        if t in matrix:
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
    }
    if "EQUIVALENT_MANUAL_DOCS" in conditions and "MEMORYCUSTODIAN" in conditions:
        for t in task_ids:
            man = matrix[t].get("EQUIVALENT_MANUAL_DOCS", {}).get("status")
            mc = matrix[t].get("MEMORYCUSTODIAN", {}).get("status")
            if man and mc:
                paired["total_pairs"] += 1
                if man == "PASS" and mc == "PASS":
                    paired["both_pass"] += 1
                elif man != "PASS" and mc != "PASS":
                    paired["both_fail"] += 1
                elif mc == "PASS" and man != "PASS":
                    paired["mc_only_pass"] += 1
                elif man == "PASS" and mc != "PASS":
                    paired["manual_only_pass"] += 1

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
        ])
    else:
        lines.append("*Both conditions were not present in this run.*")

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

    all_tasks = load_task_list(root, args.suite)
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

    record_dir = Path(args.record_dir).resolve() if args.record_dir else None
    if record_dir:
        record_dir.mkdir(parents=True, exist_ok=True)

    total_runs = len(selected_tasks) * len(selected_conditions)
    print(f"MemoryCustodian Batch Benchmark: {len(selected_tasks)} tasks x {len(selected_conditions)} conditions = {total_runs} runs.")

    if args.dry_run:
        print("Dry run requested. Planned execution matrix:")
        for t in selected_tasks:
            print(f"- {t}: {', '.join(selected_conditions)}")
        return 0

    existing_ids = get_existing_result_ids(record_dir) if (record_dir and args.resume) else set()
    records = []
    run_idx = 0

    for task_id in selected_tasks:
        for condition in selected_conditions:
            run_idx += 1
            expected_prefix = f"{args.suite}__{task_id}__"
            # If resume requested, check if already recorded
            if args.resume and record_dir:
                matching = any(
                    (condition in rid and task_id in rid and f"rep{args.repetition_id}" in rid)
                    for rid in existing_ids
                )
                if matching:
                    print(f"[{run_idx}/{total_runs}] Skip (already recorded): {task_id} [{condition}]")
                    continue

            print(f"[{run_idx}/{total_runs}] Running: {task_id} [{condition}] ...", end="", flush=True)
            record = run_single_task(
                root,
                task_id,
                condition,
                args.runtime,
                args.agent_cmd,
                args.repetition_id,
                args.timeout,
                record_dir,
                args.model_version,
                args.tool_policy,
            )
            if record:
                records.append(record)
                status = record.get("status", "BLOCKER")
                labels = record.get("failure_labels", [])
                label_str = f" ({', '.join(labels)})" if labels else ""
                print(f" {status}{label_str}")
            else:
                print(" ERROR (no record)")

    summary = aggregate_results(selected_tasks, selected_conditions, records)

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
        print(f"\nReport written to: {rf}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
