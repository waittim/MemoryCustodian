"""Grade a checkout with a hidden Python oracle.

The oracle prints ``LABEL <CODE>`` and exits 1 for a graded failure.
Exit 0 with no labels is PASS. Any other exit is BLOCKER.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time


LABEL_LINE = re.compile(r"^LABEL ([A-Z][A-Z0-9_]*)$")
FAILURE_LABELS = {
    "MEMORY_OMISSION",
    "MEMORY_FALSE_POSITIVE",
    "MEMORY_STALE_USE",
    "MEMORY_AUTHORITY_VIOLATION",
    "MEMORY_CONFLICT_MISSED",
    "MEMORY_CONTEXT_OVERLOAD",
    "MEMORY_NONE",
}


def grade_script(script: Path, checkout: Path, lib_dir: Path) -> dict:
    """Run one oracle against a prepared checkout."""

    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(lib_dir), str(checkout)))
    env.pop("PYTHONHOME", None)
    try:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=checkout,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _result(
            "BLOCKER",
            [],
            f"oracle timed out: {script.name}",
            time.monotonic() - started,
            None,
        )
    except OSError as exc:
        return _result(
            "BLOCKER",
            [],
            f"oracle could not start: {exc}",
            time.monotonic() - started,
            None,
        )

    elapsed = time.monotonic() - started
    labels = []
    for line in completed.stdout.splitlines():
        match = LABEL_LINE.match(line.strip())
        if match:
            labels.append(match.group(1))
    unknown = sorted({label for label in labels if label not in FAILURE_LABELS})
    if unknown:
        return _result(
            "BLOCKER",
            [],
            "unknown failure label: " + ", ".join(unknown),
            elapsed,
            completed.returncode,
        )
    deduped = _dedupe(labels)
    detail = _tail(completed.stderr)
    if completed.returncode == 0:
        if deduped:
            return _result("BLOCKER", [], "PASS oracle emitted a failure label", elapsed, 0)
        return _result("PASS", [], "", elapsed, 0)
    if completed.returncode == 1:
        if not deduped:
            deduped = ["MEMORY_OMISSION"]
        return _result("FAIL", deduped, detail, elapsed, 1)
    return _result(
        "BLOCKER",
        [],
        detail or f"oracle exit {completed.returncode}",
        elapsed,
        completed.returncode,
    )


def run_visible_tests(checkout: Path, command: list[str]) -> str:
    """Return PASS, FAIL, or BLOCKER for the fixture's visible tests."""

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(checkout)
    env.pop("PYTHONHOME", None)
    try:
        completed = subprocess.run(
            command,
            cwd=checkout,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "BLOCKER"
    if completed.returncode == 0:
        return "PASS"
    return "FAIL"


def _result(status: str, labels: list[str], detail: str, elapsed: float, exit_code: int | None) -> dict:
    memory_label = None
    if status == "PASS":
        memory_label = "MEMORY_NONE"
    elif labels:
        memory_label = labels[0]
    return {
        "status": status,
        "failure_labels": labels,
        "memory_label": memory_label,
        "detail": detail,
        "exit_code": exit_code,
        "metrics": {
            "task_success": status == "PASS",
            "hard_constraint_violation": "MEMORY_AUTHORITY_VIOLATION" in labels,
            "memory_dependent_requirement_satisfied": status == "PASS",
            "stale_memory_used": "MEMORY_STALE_USE" in labels,
            "unsupported_memory_used": "MEMORY_FALSE_POSITIVE" in labels,
            "routing_complete": None,
            "context_memory_tokens": None,
            "total_input_tokens": None,
            "total_output_tokens": None,
            "wall_clock_seconds": round(elapsed, 6),
            "tool_calls": None,
            "repeated_file_reads": None,
            "tests_run": None,
            "final_test_status": None,
        },
    }


def _dedupe(labels: list[str]) -> list[str]:
    ordered = []
    for label in labels:
        if label not in ordered:
            ordered.append(label)
    return ordered


def _tail(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= 500:
        return stripped
    return stripped[-500:]
