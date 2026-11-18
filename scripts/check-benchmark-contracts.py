#!/usr/bin/env python3
"""Validate an explicit benchmark contract revision without running an agent."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners.harness import HarnessError
from benchmarks.runners.task_revisions import load_revision, markdown_report, run_contracts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--task-version", required=True, type=int)
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--report-file", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        revision = load_revision(ROOT, args.task, args.task_version)
        if args.record_dir and args.record_dir.exists() and any(args.record_dir.iterdir()):
            raise HarnessError("use a new empty contract record directory")
        if args.report_file and args.report_file.exists():
            raise HarnessError("contract report already exists; use a new sample path")
        records = run_contracts(ROOT, revision)
        if args.record_dir:
            args.record_dir.mkdir(parents=True, exist_ok=True)
            inventory = []
            for record in records:
                path = args.record_dir / (record["result_id"] + ".json")
                payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
                with path.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(payload)
                inventory.append(hashlib.sha256(payload.encode()).hexdigest() + "  " + path.name)
            with (args.record_dir / "SHA256SUMS").open("x", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(inventory) + "\n")
        if args.report_file:
            args.report_file.parent.mkdir(parents=True, exist_ok=True)
            with args.report_file.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(markdown_report(records))
        if args.format == "json":
            print(json.dumps(records, indent=2, sort_keys=True))
        else:
            passed = sum(record["status"] == "PASS" for record in records)
            print(f"Benchmark contract revision: {'OK' if passed == len(records) else 'FAIL'}")
            print(f"Task: {args.task} v{args.task_version}; contract cases: {passed}/{len(records)}")
            print("Offline contract evidence only; historical agent results were not regraded.")
        return 2 if any(record["status"] == "BLOCKER" for record in records) else int(any(record["status"] != "PASS" for record in records))
    except (HarnessError, OSError, UnicodeError, ValueError) as exc:
        print(f"Benchmark contract revision: FAIL ({exc})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
