#!/usr/bin/env python3
"""Run the fixed 0.14 development interruption screen, independently of core."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners.harness import HarnessError, git_dirty, git_head, load_tasks
from benchmarks.runners.interruption import CONDITIONS, POLICY, TASKS, run_pair


def write_new(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def report(rows: list[dict], metadata: dict) -> str:
    valid = [row for row in rows if row["status"] == "COMPLETE"]
    lines = ["# Development interruption experiment results", "",
             f"Generated: {metadata['generated_at']}",
             f"Runtime: {metadata['cli_version']}; requested model: {metadata['model']}; reasoning: low.",
             "", "Development fixtures only; no general effectiveness or long-horizon claim.", "",
             "| Task | Repetition | Block | FRESH | OBSERVABLE_CHECKPOINT | NATIVE_RESUME |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in sorted(rows, key=lambda value: (value["task_id"], value["repetition"])):
        cells = {cell["condition"]: cell["status"] for cell in row["conditions"]}
        lines.append("| " + " | ".join([row["task_id"], str(row["repetition"]), row["status"]]
                                          + [cells.get(key, "—") for key in CONDITIONS]) + " |")
    lines += ["", f"Complete three-condition pairs: {len(valid)}/{len(rows)}.", "",
              "| Condition | PASS / valid pairs | Mean tools | Mean input tokens | Mean output tokens | Mean seconds |",
              "| --- | --- | --- | --- | --- | --- |"]
    for condition in CONDITIONS:
        cells = [next(cell for cell in row["conditions"] if cell["condition"] == condition) for row in valid]
        means = []
        for key in ("tool_calls", "total_input_tokens", "total_output_tokens", "wall_clock_seconds"):
            values = [cell["runtime"].get(key) for cell in cells]
            means.append(f"{sum(values) / len(values):.1f}" if values and all(value is not None for value in values) else "unobserved")
        lines.append("| " + " | ".join([condition, f"{sum(cell['status'] == 'PASS' for cell in cells)}/{len(cells)}"] + means) + " |")
    native_failures = sum(next(cell for cell in row["conditions"] if cell["condition"] == "NATIVE_RESUME")["status"] == "FAIL" for row in valid)
    wins = sum(next(cell for cell in row["conditions"] if cell["condition"] == "NATIVE_RESUME")["status"] == "FAIL"
               and next(cell for cell in row["conditions"] if cell["condition"] == "OBSERVABLE_CHECKPOINT")["status"] == "PASS" for row in valid)
    lines += ["", "## Gate interpretation", "",
              f"Native continuation failures in valid pairs: {native_failures}. Observable-summary wins over native: {wins}.",
              "BLOCKER and inapplicable samples are excluded from success comparisons.",
              "Repeated file reads are unobserved (null); tool events do not prove repeated reads.",
              "The checkpoint condition is an experimental observable-metadata summary, not the proposed production feature.",
              "The boundary is early (two completed tools), not representative long-horizon interruption.",
              "A small development screen cannot establish material production failures or checkpoint benefit; the 0.14 gate remains unproven.",
              "No shared protocol, authoritative routing, or durable project memory is changed by a runtime.",
              "", "## Reproduction and evidence", "",
              "See [the fixed plan](INTERRUPTION-2026-11-15.md). Append-only per-pair JSON and experiment.json",
              "record exact method/plan hashes, common-prefix session IDs, identical starting-tree hashes,",
              "interruption event counts, oracle outcomes, and post-resume metrics. Raw traces are not published.",
              "Native session history uses the CLI's normal local session store; this runner neither copies credentials nor exports that history.",
              "Token/time means describe recovery turns only, excluding common-prefix cost; no savings or latency claim follows.",
              "Native CLI usage is session-cumulative; its raw counters are retained separately and post-resume tokens stay null because no interrupted-prefix baseline is available.",
              "Do not tune these fixtures from outcomes; any follow-up sample needs a new plan and record directory.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-executable", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    options = parser.parse_args()
    if os.name != "posix" or options.timeout <= 0:
        parser.error("experiment requires POSIX process groups and a positive timeout")
    executable = shutil.which(options.codex_executable)
    if not executable:
        parser.error("Codex executable unavailable")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if not version.startswith("codex-cli "):
        parser.error("executable is not Codex CLI")
    options.record_dir.mkdir(parents=True, exist_ok=True)
    if any(options.record_dir.iterdir()) or options.report_file.exists():
        parser.error("use a new empty record directory and report file; prior results are immutable")
    paths = ("benchmarks/runners/interruption.py", "scripts/run-interruption-bench.py",
             "benchmarks/runners/codex_runtime.py", "benchmarks/runners/harness.py",
             "benchmarks/graders/mechanical.py", "docs/evaluations/benchmark/INTERRUPTION-2026-11-15.md")
    metadata = {"experiment_schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                "cli_version": version, "model": options.model_version, "policy": POLICY,
                "git_head": git_head(ROOT), "git_dirty": git_dirty(ROOT),
                "tasks": list(TASKS), "repetitions": 2, "interrupt_after_completed_tools": 2,
                "conditions": list(CONDITIONS), "timeout": options.timeout, "jobs": options.jobs,
                "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}}
    write_new(options.record_dir / "experiment.json", metadata)
    tasks = {task["task_id"]: task for task in load_tasks(ROOT)}
    rows = []
    with tempfile.TemporaryDirectory(prefix="mc-interruption-") as directory:
        work = Path(directory)
        def run(index, task_id, repetition):
            pair_work = work / f"{task_id}-{repetition}"
            pair_work.mkdir()
            try:
                row = run_pair(ROOT, tasks[task_id], pair_work, executable=executable,
                               model=options.model_version, repetition=repetition,
                               order_offset=index, timeout=options.timeout)
            except (HarnessError, OSError, ValueError, subprocess.SubprocessError):
                row = {"task_id": task_id, "repetition": repetition, "status": "BLOCKER",
                       "conditions": [], "detail": "experiment infrastructure failed; no task failure inferred"}
            row["experiment_sha256"] = hashlib.sha256((options.record_dir / "experiment.json").read_bytes()).hexdigest()
            write_new(options.record_dir / f"{task_id}__rep{repetition}.json", row)
            return row
        with ThreadPoolExecutor(max_workers=options.jobs) as pool:
            schedule = [(task_id, repetition) for task_id in TASKS for repetition in (1, 2)]
            futures = [pool.submit(run, index, *cell) for index, cell in enumerate(schedule)]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                print(json.dumps({"task": row["task_id"], "repetition": row["repetition"],
                                  "status": row["status"], "completed_pairs": len(rows)}, sort_keys=True), flush=True)
    options.report_file.parent.mkdir(parents=True, exist_ok=True)
    with options.report_file.open("x", encoding="utf-8") as handle:
        handle.write(report(rows, metadata))
    return 1 if any(row["status"] == "BLOCKER" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
