#!/usr/bin/env python3
"""Execute the fixed three-task installed-Skill live smoke, append-only."""

from __future__ import annotations

import argparse
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

from benchmarks.runners.installed_skill_live import (
    DIAGNOSTIC_PLAN, INSTRUCTIONS, METHODS, POLICY, TASK_IDS, TASKS, SmokeError, grade, make_record,
    prepare_fixture, run_runtime, runtime_argv, sha,
)


def write_new(path: Path, value: dict) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)


def report(records: list[dict], metadata: dict) -> str:
    lines = ["# Installed-Skill live smoke results", "", f"Generated: {metadata['generated_at']}",
             f"Runtime: {metadata['cli_version']}; requested model: {metadata['model']}; reasoning: low.",
             "", "Explicit installed Skill-file invocation only; automatic discovery was not tested.", "",
             "| Task | Outcome | Evidence | Diagnostic categories |", "| --- | --- | --- | --- |"]
    lines.extend(f"| {row['task_id']} | {row['status']} | {row['evidence_class']} | "
                 + (", ".join(row["runtime"].get("diagnostics", {}).get("categories", [])) or "none observed") + " |" for row in records)
    lines += ["", f"This sample selected {len(records)} of the fixed three development tasks, with one independent session each.",
              "Unselected tasks are absent from this sample, not counted as successes. Earlier records and all blockers remain retained.",
              "Error categories are coarse observations from allowlisted error fields/stderr, not confirmed root causes.",
              "This is a single-runtime workflow smoke, not effectiveness, cross-agent conformance, or checkpoint evidence.",
              "Strict-read proofs require CLI JSON content and observable event order; command mentions alone are insufficient.",
              "Raw prompts, commands, output, reasoning, messages and machine paths are not retained.",
              "Source/fixture hashes and allowlisted metadata support consistency, not tamper-proof runtime attestation.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-executable", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--tasks", nargs="+", choices=TASK_IDS, help="Explicit independent sample subset; omitting selects all three fixed tasks.")
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    args = parser.parse_args(argv)
    selected_tasks = list(args.tasks or TASK_IDS)
    if len(set(selected_tasks)) != len(selected_tasks):
        parser.error("selected tasks must be unique")
    if os.name != "posix":
        parser.error("this development adapter requires POSIX process groups")
    executable = shutil.which(args.codex_executable)
    if not executable:
        parser.error("Codex executable unavailable")
    args.record_dir.mkdir(parents=True, exist_ok=True)
    if any(args.record_dir.iterdir()) or args.report_file.exists():
        parser.error("use a new empty record directory and a new report path")
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if not version.startswith("codex-cli "):
            raise SmokeError("executable did not identify as Codex CLI")
        source_hashes = {name: sha((ROOT / name).read_bytes()) for name in METHODS}
        metadata = {"installed_skill_experiment_format": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                    "cli_version": version, "cli_binary_sha256": sha(Path(executable).read_bytes()),
                    "model": args.model_version, "policy": POLICY, "timeout_seconds": 180,
                    "tasks": selected_tasks, "original_cohort_tasks": list(TASK_IDS),
                    "diagnostics_schema_version": 1, "plan": DIAGNOSTIC_PLAN,
                    "source_sha256": source_hashes}
        write_new(args.record_dir / "experiment.json", metadata)
        records, sessions = [], set()
        with tempfile.TemporaryDirectory(prefix="memory-installed-live-") as directory:
            scratch = Path(directory)
            for task in selected_tasks:
                fixture = {"task_id": task}
                runtime = {"status": "BLOCKER", "evidence_class": "live-runtime-unavailable"}
                try:
                    checkout, state = scratch / task, scratch / (task + "-state")
                    fixture = prepare_fixture(ROOT, checkout, state, task)
                    runtime = run_runtime(runtime_argv(executable, args.model_version, checkout, state),
                                          checkout, state, INSTRUCTIONS + TASKS[task], timeout=180,
                                          evidence_class="live-runtime")
                    if runtime.get("thread_id") in sessions:
                        outcome = {"status": "BLOCKER", "detail": "runtime session identity was reused"}
                    else:
                        if runtime.get("thread_id"):
                            sessions.add(runtime["thread_id"])
                        outcome = grade(checkout, state, fixture, runtime)
                    if runtime.get("evidence_class") != "live-runtime":
                        outcome = {"status": "BLOCKER", "detail": "a runtime stub is not live evidence"}
                    if runtime.get("status") != "COMPLETED":
                        runtime["evidence_class"] = "live-runtime-unavailable"
                except (SmokeError, OSError, ValueError, subprocess.SubprocessError):
                    outcome = {"status": "BLOCKER", "detail": "fixture preparation or verification unavailable"}
                if any(sha((ROOT / name).read_bytes()) != value for name, value in source_hashes.items()):
                    outcome = {"status": "BLOCKER", "detail": "method sources changed during collection"}
                record = make_record(fixture, runtime, outcome, metadata)
                write_new(args.record_dir / (record["result_id"] + ".json"), record)
                records.append(record)
                print(json.dumps({"task": task, "status": record["status"]}), flush=True)
        inventory = [sha(path.read_bytes()) + "  " + path.name for path in sorted(args.record_dir.glob("*.json"))]
        with (args.record_dir / "SHA256SUMS").open("xb") as handle:
            handle.write(("\n".join(inventory) + "\n").encode("utf-8"))
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        with args.report_file.open("xb") as handle:
            handle.write(report(records, metadata).encode("utf-8"))
        return 2 if any(row["status"] == "BLOCKER" for row in records) else int(any(row["status"] != "PASS" for row in records))
    except (SmokeError, OSError, ValueError, subprocess.SubprocessError):
        print("Installed-Skill smoke unavailable; no live success inferred.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
