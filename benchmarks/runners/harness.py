"""Prepare isolated benchmark checkouts and grade them offline.

This module does not select authoritative memory and does not write
``docs/memory/``. Derived checkouts live in a temp directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


from benchmarks.graders.mechanical import grade_script, run_visible_tests


CONDITIONS = (
    "NO_MEMORY",
    "PLATFORM_FILE_ONLY",
    "EQUIVALENT_MANUAL_DOCS",
    "MEMORYCUSTODIAN",
)
STATUSES = ("PASS", "REVIEW", "FAIL", "BLOCKER")
CATEGORIES = (
    "constraint-sensitive-implementation",
    "architecture-planning",
    "bug-fixing",
    "refactoring",
    "history-prior-decision",
    "stale-or-conflicting-memory",
)
FAILURE_LABELS = (
    "MEMORY_OMISSION",
    "MEMORY_FALSE_POSITIVE",
    "MEMORY_STALE_USE",
    "MEMORY_AUTHORITY_VIOLATION",
    "MEMORY_CONFLICT_MISSED",
    "MEMORY_CONTEXT_OVERLOAD",
    "MEMORY_NONE",
)
STANDARD_HIDE = {
    "NO_MEMORY": ["docs/manual", "docs/memory"],
    "PLATFORM_FILE_ONLY": ["docs/manual", "docs/memory"],
    "EQUIVALENT_MANUAL_DOCS": ["docs/memory"],
    "MEMORYCUSTODIAN": ["docs/manual"],
}
TASK_KEYS = {
    "baseline_notes",
    "category",
    "condition_visibility",
    "expected_touched_paths",
    "forbidden_actions",
    "information_parity_check",
    "memory_dependencies",
    "offline_expectations",
    "repo",
    "required_constraints",
    "split",
    "success_oracle",
    "suite",
    "task_format",
    "task_id",
    "task_prompt",
    "task_version",
    "test_command",
}
PARITY_KEYS = {"exclusive_facts", "facts", "manual_paths", "memory_paths"}
TEXT_SUFFIXES = {".json", ".md", ".py", ".txt"}
SKIP_PARTS = {"__pycache__", ".git"}
TASK_OVERLAY_FILES = {"ledger.py", "router.py"}
SOLUTION_FILES = {"CONFLICT_REPORT.txt", "PLAN.md", "export.py", "ledger.py", "router.py"}
RESULT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{8,240}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class HarnessError(RuntimeError):
    """The benchmark harness itself failed closed."""


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def load_manifest(root: Path) -> dict:
    path = root / "benchmarks" / "benchmark-manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"benchmark manifest is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise HarnessError("benchmark manifest must be an object")
    return payload


def load_tasks(root: Path) -> list[dict]:
    tasks_dir = root / "benchmarks" / "tasks"
    if not tasks_dir.is_dir():
        raise HarnessError("benchmarks/tasks is missing")
    tasks = []
    seen = set()
    for path in sorted(tasks_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HarnessError(f"{path.name} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise HarnessError(f"{path.name} must contain an object")
        task_id = payload.get("task_id")
        if task_id in seen:
            raise HarnessError(f"duplicate task id: {task_id}")
        seen.add(task_id)
        if path.stem != task_id:
            raise HarnessError(f"{path.name} does not match task_id {task_id}")
        tasks.append(payload)
    return tasks


def package_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', text)
    if not match:
        raise HarnessError("pyproject.toml has no version")
    return match.group(1)


def host_protocol(root: Path) -> str:
    text = (root / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8")
    match = re.search(r"(?m)^- protocol_version:\s*(\S+)\s*$", text)
    if not match:
        raise HarnessError("host manifest has no protocol_version")
    return match.group(1)


def git_head(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    return value


def tree_hash(root: Path, skip_prefixes: tuple[str, ...] = ()) -> str:
    rows = []
    for path in iter_files(root, skip_prefixes):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{relative}\t{digest}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def iter_files(root: Path, skip_prefixes: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise HarnessError(f"symlink is not allowed: {path}")
        relative_path = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative_path.parts):
            continue
        if path.name == ".DS_Store":
            continue
        relative = relative_path.as_posix()
        if any(_matches_prefix(relative, prefix) for prefix in skip_prefixes):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def validate_manifest(manifest: dict) -> list[str]:
    issues = []
    expected = {
        "benchmark_format": "1",
        "task_format": "1",
        "result_format": "1",
        "protocol": "0.8",
        "entry_schema": "3",
        "changes_shared_protocol": False,
        "suite": "core",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            issues.append(f"manifest {key} must be {value!r}")
    if manifest.get("conditions") != list(CONDITIONS):
        issues.append("manifest conditions drifted from the runner contract")
    if manifest.get("failure_labels") != list(FAILURE_LABELS):
        issues.append("manifest failure labels drifted from the runner contract")
    if manifest.get("standard_hide") != STANDARD_HIDE:
        issues.append("manifest standard_hide drifted from the runner contract")
    if manifest.get("primary_comparison") != ["EQUIVALENT_MANUAL_DOCS", "MEMORYCUSTODIAN"]:
        issues.append("primary comparison must be the information-matched pair")
    return issues


def validate_task(task: dict, root: Path, manifest: dict) -> list[str]:
    issues = []
    prefix = str(task.get("task_id") or "<missing>")
    if set(task) != TASK_KEYS:
        missing = sorted(TASK_KEYS - set(task))
        extra = sorted(set(task) - TASK_KEYS)
        if missing:
            issues.append(f"{prefix}: missing {', '.join(missing)}")
        if extra:
            issues.append(f"{prefix}: unknown {', '.join(extra)}")
        return issues
    if task["task_format"] != "1":
        issues.append(f"{prefix}: task_format must be 1")
    if not isinstance(task["task_version"], int) or task["task_version"] < 1:
        issues.append(f"{prefix}: task_version must be a positive integer")
    if task["suite"] != manifest.get("suite"):
        issues.append(f"{prefix}: suite does not match the manifest")
    if task["split"] != "pilot-development":
        issues.append(f"{prefix}: split must stay pilot-development")
    if task["category"] not in CATEGORIES:
        issues.append(f"{prefix}: unknown category")
    if not isinstance(task["task_prompt"], str) or not task["task_prompt"].strip():
        issues.append(f"{prefix}: task_prompt is empty")
    repo = task["repo"]
    if not isinstance(repo, dict) or set(repo) != {"commit", "id", "root"}:
        issues.append(f"{prefix}: repo must pin id, root, and commit")
    else:
        if repo["root"] != f"benchmarks/fixtures/{repo['id']}":
            issues.append(f"{prefix}: repo root does not match its id")
        if not HEX64_RE.fullmatch(str(repo["commit"])):
            issues.append(f"{prefix}: repo commit must be a sha256 fixture hash")
        fixture = root / repo["root"]
        if not fixture.is_dir():
            issues.append(f"{prefix}: fixture directory is missing")
    for name in (
        "expected_touched_paths",
        "required_constraints",
        "forbidden_actions",
        "memory_dependencies",
    ):
        if not _string_list(task[name]):
            issues.append(f"{prefix}: {name} must be a non-empty string list")
    if task["condition_visibility"] != {
        condition: {"hide": list(paths)} for condition, paths in STANDARD_HIDE.items()
    }:
        issues.append(f"{prefix}: condition_visibility must use the standard hide map")
    parity = task["information_parity_check"]
    if not isinstance(parity, dict) or set(parity) != PARITY_KEYS:
        issues.append(f"{prefix}: information_parity_check fields are incomplete")
    elif not _string_list(parity["facts"]):
        issues.append(f"{prefix}: facts must be a non-empty string list")
    elif not isinstance(parity["exclusive_facts"], list) or not all(
        isinstance(item, str) and item for item in parity["exclusive_facts"]
    ):
        issues.append(f"{prefix}: exclusive_facts must be a list of strings")
    elif not _string_list(parity["memory_paths"]) or not _string_list(parity["manual_paths"]):
        issues.append(f"{prefix}: parity paths must be non-empty string lists")
    else:
        for fact in parity["facts"]:
            if fact in task["task_prompt"] or fact in task["baseline_notes"]:
                issues.append(f"{prefix}: prompt or notes repeat a parity fact")
            for action in task["forbidden_actions"]:
                if fact in action:
                    issues.append(f"{prefix}: forbidden action repeats a parity fact")
    command = task["test_command"]
    if not _string_list(command) or command.count("{python}") != 1:
        issues.append(f"{prefix}: test_command must be an argv list with one {{python}} token")
    oracle = task["success_oracle"]
    expected_script = f"benchmarks/oracles/{task['task_id']}/check.py"
    if oracle != {"kind": "hidden-python", "script": expected_script}:
        issues.append(f"{prefix}: success oracle must be the hidden check.py")
    elif not (root / expected_script).is_file():
        issues.append(f"{prefix}: hidden oracle is missing")
    expectations = task["offline_expectations"]
    if not isinstance(expectations, dict) or set(expectations) != {
        "negatives",
        "reference_dir",
        "starter_labels",
    }:
        issues.append(f"{prefix}: offline_expectations fields are incomplete")
    else:
        if not _string_list(expectations["starter_labels"]):
            issues.append(f"{prefix}: starter_labels must be a non-empty string list")
        elif any(label not in FAILURE_LABELS or label == "MEMORY_NONE" for label in expectations["starter_labels"]):
            issues.append(f"{prefix}: starter_labels contain an invalid label")
        reference = root / expectations["reference_dir"]
        if expectations["reference_dir"] != f"benchmarks/references/{task['task_id']}":
            issues.append(f"{prefix}: reference_dir must match the task id")
        elif not reference.is_dir():
            issues.append(f"{prefix}: reference directory is missing")
        else:
            issues.extend(_overlay_issues(reference, SOLUTION_FILES, f"{prefix} reference"))
        if not isinstance(expectations["negatives"], list):
            issues.append(f"{prefix}: negatives must be a list")
        else:
            for negative in expectations["negatives"]:
                if not isinstance(negative, dict) or set(negative) != {"dir", "labels"}:
                    issues.append(f"{prefix}: negative entries need dir and labels")
                    continue
                if not _string_list(negative["labels"]):
                    issues.append(f"{prefix}: negative labels are empty")
                negative_dir = root / negative["dir"]
                if not negative_dir.is_dir():
                    issues.append(f"{prefix}: negative directory is missing")
                else:
                    issues.extend(_overlay_issues(negative_dir, SOLUTION_FILES, f"{prefix} negative"))
    return issues


def prepare_checkout(root: Path, task: dict, condition: str, dest: Path) -> None:
    if condition not in CONDITIONS:
        raise HarnessError(f"unknown condition: {condition}")
    fixture = root / task["repo"]["root"]
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise HarnessError("checkout destination is not empty")
    copy_tree(fixture, dest, ("_conditions", "_tasks"))
    overlay = fixture / "_tasks" / task["task_id"]
    if overlay.exists():
        issues = _overlay_issues(overlay, TASK_OVERLAY_FILES, task["task_id"], allow_docs=True)
        if issues:
            raise HarnessError("; ".join(issues))
        copy_tree(overlay, dest, ())
    for relative in STANDARD_HIDE[condition]:
        _remove_relative(dest, relative)
    condition_dir = fixture / "_conditions" / condition
    if condition_dir.exists():
        issues = _overlay_issues(condition_dir, {"AGENTS.md"}, f"{condition} bootstrap")
        if issues:
            raise HarnessError("; ".join(issues))
        copy_tree(condition_dir, dest, ())
    for leftover in ("_conditions", "_tasks"):
        path = dest / leftover
        if path.exists():
            shutil.rmtree(path)


def isolation_issues(checkout: Path, condition: str) -> list[str]:
    issues = []
    required_absent = list(STANDARD_HIDE[condition]) + ["_conditions", "_tasks"]
    if condition == "NO_MEMORY":
        required_absent.append("AGENTS.md")
    for relative in required_absent:
        if (checkout / relative).exists():
            issues.append(f"{condition}: {relative} remained visible")
    required_present = ["AGENTS.md"]
    if condition == "EQUIVALENT_MANUAL_DOCS":
        required_present.append("docs/manual")
    elif condition == "MEMORYCUSTODIAN":
        required_present.append("docs/memory")
    if condition != "NO_MEMORY":
        for relative in required_present:
            if not (checkout / relative).exists():
                issues.append(f"{condition}: {relative} was not visible")
    for path in iter_files(checkout, ()):
        if path.name in {"oracle_support.py", "check.py"}:
            issues.append(f"{condition}: hidden grader file was copied: {path.name}")
    return issues


def parity_issues(task: dict, condition: str, checkout: Path) -> list[str]:
    parity = task["information_parity_check"]
    facts = parity["facts"]
    blob = combined_text(checkout)
    issues = []
    if condition in {"NO_MEMORY", "PLATFORM_FILE_ONLY"}:
        for fact in facts:
            if fact in blob:
                issues.append(f"{task['task_id']}: {condition} leaked a parity fact")
        return issues
    path_key = "memory_paths" if condition == "MEMORYCUSTODIAN" else "manual_paths"
    for fact in facts:
        if fact not in blob:
            issues.append(f"{task['task_id']}: {condition} is missing a parity fact")
            continue
        if not any(fact in _read(checkout / relative) for relative in parity[path_key]):
            issues.append(f"{task['task_id']}: {condition} fact is outside the declared corpus")
    return issues


def exclusive_issues(tasks: list[dict], blobs: dict[str, str]) -> list[str]:
    issues = []
    for task in tasks:
        for fact in task["information_parity_check"]["exclusive_facts"]:
            for other_id, blob in blobs.items():
                if other_id != task["task_id"] and fact in blob:
                    issues.append(f"{task['task_id']}: exclusive fact leaked into {other_id}")
    return issues


def combined_text(root: Path) -> str:
    chunks = []
    for path in iter_files(root, ()):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def apply_solution(source: Path, checkout: Path) -> None:
    issues = _overlay_issues(source, SOLUTION_FILES, source.name)
    if issues:
        raise HarnessError("; ".join(issues))
    copy_tree(source, checkout, ())


def grade_checkout(root: Path, task: dict, checkout: Path) -> dict:
    script = root / task["success_oracle"]["script"]
    lib_dir = root / "benchmarks" / "oracles" / "_lib"
    return grade_script(script, checkout, lib_dir)


def command_for(task: dict) -> list[str]:
    return [sys.executable if part == "{python}" else part for part in task["test_command"]]


def make_result_id(task: dict, condition: str, runtime: str, repetition: str, fixture_hash: str) -> str:
    return (
        f"{task['suite']}__{task['task_id']}__v{task['task_version']}"
        f"__{condition}__{runtime}__rep{repetition}__{fixture_hash[:12]}"
    )


def build_record(
    *,
    root: Path,
    task: dict,
    condition: str,
    runtime: str,
    repetition: str,
    evidence_class: str,
    status: str,
    failure_labels: list[str],
    memory_label: str | None,
    metrics: dict,
    detail: str,
    fixture_hash: str,
    visible_hash: str,
    model_version: str,
    tool_policy: str,
) -> dict:
    if status not in STATUSES:
        raise HarnessError(f"invalid status {status}")
    result_id = make_result_id(task, condition, runtime, repetition, fixture_hash)
    if not RESULT_ID_RE.fullmatch(result_id):
        raise HarnessError(f"unsafe result id: {result_id}")
    return {
        "result_format": "1",
        "result_id": result_id,
        "status": status,
        "evidence_class": evidence_class,
        "suite": task["suite"],
        "task_id": task["task_id"],
        "task_version": task["task_version"],
        "condition": condition,
        "runtime": runtime,
        "model_version": model_version or None,
        "tool_policy": tool_policy or None,
        "budget": {"time_seconds": None, "token_limit": None},
        "repetition_id": repetition,
        "package_version": package_version(root),
        "protocol_version": host_protocol(root),
        "git_commit": git_head(root),
        "os": platform.platform(),
        "prompt_sha256": hashlib.sha256(task["task_prompt"].encode("utf-8")).hexdigest(),
        "visible_source_sha256": visible_hash,
        "fixture_sha256": fixture_hash,
        "checkout_id": visible_hash,
        "failure_labels": failure_labels,
        "memory_label": memory_label,
        "detail": detail,
        "metrics": metrics,
    }


def write_result(directory: Path, record: dict) -> Path:
    if record.get("status") not in STATUSES:
        raise HarnessError("refusing to write a result without a known status")
    if not RESULT_ID_RE.fullmatch(str(record.get("result_id", ""))):
        raise HarnessError("refusing to write a result with an unsafe id")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['result_id']}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise FileExistsError(f"result already exists: {path.name}") from exc
    return path


def check_integrity(root: Path | None = None) -> list[str]:
    suite_root = root or repo_root_from_here()
    manifest = load_manifest(suite_root)
    issues = validate_manifest(manifest)
    if host_protocol(suite_root) != manifest.get("protocol"):
        issues.append("host protocol_version does not match the benchmark manifest")
    try:
        tasks = load_tasks(suite_root)
    except HarnessError as exc:
        return issues + [str(exc)]
    if not 12 <= len(tasks) <= 18:
        issues.append(f"pilot task count must be 12-18, found {len(tasks)}")
    repos = {task["repo"]["id"] for task in tasks if isinstance(task.get("repo"), dict)}
    if len(repos) < 2:
        issues.append("pilot must pin at least two repositories")
    if set(task["category"] for task in tasks if "category" in task) != set(CATEGORIES):
        issues.append("pilot must include every task category")
    fixture_hashes = {}
    for task in tasks:
        issues.extend(validate_task(task, suite_root, manifest))
        repo = task.get("repo")
        if not isinstance(repo, dict):
            continue
        fixture = suite_root / str(repo.get("root", ""))
        if not fixture.is_dir():
            continue
        digest = fixture_hashes.get(repo["id"])
        if digest is None:
            before = tree_hash(fixture)
            fixture_hashes[repo["id"]] = before
            digest = before
        if repo.get("commit") != digest:
            issues.append(f"{task['task_id']}: fixture hash does not match the pinned commit")
    if issues:
        return issues

    blobs = {}
    scratch = suite_root / "benchmarks" / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="integrity-") as name:
        temp_root = Path(name)
        for task in tasks:
            for condition in CONDITIONS:
                checkout = temp_root / f"{task['task_id']}-{condition}"
                prepare_checkout(suite_root, task, condition, checkout)
                issues.extend(isolation_issues(checkout, condition))
                issues.extend(parity_issues(task, condition, checkout))
                if condition != "MEMORYCUSTODIAN":
                    continue
                blobs[task["task_id"]] = combined_text(checkout)
                visible = run_visible_tests(checkout, command_for(task))
                if visible != "PASS":
                    issues.append(f"{task['task_id']}: visible starter tests {visible}")
                starter = grade_checkout(suite_root, task, checkout)
                if starter["failure_labels"] != task["offline_expectations"]["starter_labels"]:
                    issues.append(
                        f"{task['task_id']}: starter labels {starter['failure_labels']}, "
                        f"expected {task['offline_expectations']['starter_labels']}; {starter['detail']}"
                    )
                if starter["status"] != "FAIL":
                    issues.append(f"{task['task_id']}: starter grade status {starter['status']}")
                reference_checkout = temp_root / f"{task['task_id']}-reference"
                prepare_checkout(suite_root, task, condition, reference_checkout)
                apply_solution(suite_root / task["offline_expectations"]["reference_dir"], reference_checkout)
                if run_visible_tests(reference_checkout, command_for(task)) != "PASS":
                    issues.append(f"{task['task_id']}: reference broke visible tests")
                graded = grade_checkout(suite_root, task, reference_checkout)
                if graded["status"] != "PASS" or graded["failure_labels"]:
                    issues.append(
                        f"{task['task_id']}: reference grade {graded['status']} "
                        f"{graded['failure_labels']} {graded['detail']}"
                    )
                for negative in task["offline_expectations"]["negatives"]:
                    negative_checkout = temp_root / f"{task['task_id']}-negative-{Path(negative['dir']).name}"
                    prepare_checkout(suite_root, task, condition, negative_checkout)
                    apply_solution(suite_root / negative["dir"], negative_checkout)
                    graded_negative = grade_checkout(suite_root, task, negative_checkout)
                    if graded_negative["failure_labels"] != negative["labels"]:
                        issues.append(
                            f"{task['task_id']}: negative labels {graded_negative['failure_labels']}, "
                            f"expected {negative['labels']}"
                        )
        issues.extend(exclusive_issues(tasks, blobs))
        for repo_id, digest in fixture_hashes.items():
            again = tree_hash(suite_root / "benchmarks" / "fixtures" / repo_id)
            if again != digest:
                issues.append(f"{repo_id}: fixture hash changed during the run")
    agents = {}
    for repo_id in repos:
        for condition in CONDITIONS:
            if condition == "NO_MEMORY":
                continue
            path = suite_root / "benchmarks" / "fixtures" / repo_id / "_conditions" / condition / "AGENTS.md"
            if not path.is_file():
                issues.append(f"{repo_id}: missing {condition} bootstrap")
                continue
            agents.setdefault(repo_id, set()).add(path.read_text(encoding="utf-8"))
        if repo_id in agents and len(agents[repo_id]) != 3:
            issues.append(f"{repo_id}: condition bootstraps are not distinct")
    return issues


def plan_payload(root: Path, tasks: list[dict], runtime: str, conditions: list[str]) -> dict:
    plans = []
    hashes = {}
    scratch = root / "benchmarks" / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="plan-") as name:
        temp_root = Path(name)
        for task in tasks:
            repo_id = task["repo"]["id"]
            if repo_id not in hashes:
                hashes[repo_id] = tree_hash(root / task["repo"]["root"])
            for condition in conditions:
                checkout = temp_root / f"{task['task_id']}-{condition}"
                prepare_checkout(root, task, condition, checkout)
                plans.append(
                    {
                        "task_id": task["task_id"],
                        "condition": condition,
                        "runtime": runtime,
                        "prompt_sha256": hashlib.sha256(task["task_prompt"].encode("utf-8")).hexdigest(),
                        "visible_source_sha256": tree_hash(checkout),
                        "fixture_sha256": hashes[repo_id],
                        "evidence_class": "plan",
                    }
                )
    return {
        "dry_run": True,
        "suite": "core",
        "runtime": runtime,
        "package_version": package_version(root),
        "protocol_version": host_protocol(root),
        "git_commit": git_head(root),
        "os": platform.platform(),
        "plans": plans,
    }


def grade_mode(
    root: Path,
    tasks: list[dict],
    *,
    condition: str,
    runtime: str,
    repetition: str,
    grade: str,
    evidence_class: str,
    tool_policy: str,
    model_version: str,
    command: list[str] | None,
    timeout: int = 30,
) -> list[dict]:
    records = []
    scratch = root / "benchmarks" / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="grade-") as name:
        temp_root = Path(name)
        for task in tasks:
            checkout = temp_root / task["task_id"]
            prepare_checkout(root, task, condition, checkout)
            if command:
                try:
                    completed = subprocess.run(
                        command,
                        cwd=checkout,
                        text=True,
                        input=task["task_prompt"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=timeout,
                        check=False,
                    )
                    if completed.returncode != 0:
                        records.append(
                            _environment_record(
                                root,
                                task,
                                condition,
                                runtime,
                                repetition,
                                evidence_class,
                                "BLOCKER",
                                [],
                                None,
                                f"command adapter exit {completed.returncode}",
                                checkout,
                            )
                        )
                        continue
                except subprocess.TimeoutExpired:
                    records.append(
                        _environment_record(
                            root,
                            task,
                            condition,
                            runtime,
                            repetition,
                            evidence_class,
                            "BLOCKER",
                            [],
                            None,
                            f"command adapter timed out after {timeout}s",
                            checkout,
                        )
                    )
                    continue
            elif grade == "reference":
                apply_solution(root / task["offline_expectations"]["reference_dir"], checkout)
            graded = grade_checkout(root, task, checkout)
            visible = run_visible_tests(checkout, command_for(task))
            graded["metrics"]["tests_run"] = True
            graded["metrics"]["final_test_status"] = visible
            record = _environment_record(
                root,
                task,
                condition,
                runtime,
                repetition,
                evidence_class,
                graded["status"],
                graded["failure_labels"],
                graded["memory_label"],
                graded["detail"],
                checkout,
            )
            record["metrics"] = graded["metrics"]
            record["tool_policy"] = tool_policy
            record["model_version"] = model_version or None
            records.append(record)
    return records


def blocker_record(root: Path, task: dict, condition: str, runtime: str, repetition: str, reason: str) -> dict:
    scratch = root / "benchmarks" / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="blocker-") as name:
        checkout = Path(name) / "checkout"
        prepare_checkout(root, task, condition, checkout)
        return _environment_record(
            root,
            task,
            condition,
            runtime,
            repetition,
            "live-runtime-unavailable",
            "BLOCKER",
            [],
            None,
            reason,
            checkout,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or verify the MemoryCustodian benchmark harness.")
    parser.add_argument("--check-integrity", action="store_true")
    parser.add_argument("--suite", default="core")
    parser.add_argument("--runtime", default="offline-fixture")
    parser.add_argument("--condition", action="append", default=[])
    parser.add_argument("--task")
    parser.add_argument("--mode", choices=("plan", "offline-fixture", "command", "live"), default="plan")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--grade", choices=("reference", "starter"), default="reference")
    parser.add_argument("--record-dir")
    parser.add_argument("--repetition-id", default="1")
    parser.add_argument("--agent-cmd")
    parser.add_argument("--model-version", default="")
    parser.add_argument("--tool-policy", default="")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    root = repo_root_from_here()
    try:
        if args.check_integrity:
            return _print_integrity(root)
        if args.suite != "core":
            print("only the core suite is defined", file=sys.stderr)
            return 1
        manifest = load_manifest(root)
        issues = validate_manifest(manifest)
        tasks = [task for task in load_tasks(root) if task.get("suite") == args.suite]
        if args.task:
            tasks = [task for task in tasks if task.get("task_id") == args.task]
            if not tasks:
                print(f"unknown task: {args.task}", file=sys.stderr)
                return 1
        for task in tasks:
            issues.extend(validate_task(task, root, manifest))
        if issues:
            print("\n".join(issues), file=sys.stderr)
            return 1
        conditions = args.condition or list(CONDITIONS)
        unknown = [item for item in conditions if item not in CONDITIONS]
        if unknown:
            print("unknown condition: " + ", ".join(unknown), file=sys.stderr)
            return 1
        if args.dry_run or args.mode == "plan":
            payload = plan_payload(root, tasks, args.runtime, conditions)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if len(conditions) != 1:
            print("grade and live modes take one --condition", file=sys.stderr)
            return 1
        condition = conditions[0]
        if args.mode == "live":
            records = [
                blocker_record(
                    root,
                    task,
                    condition,
                    args.runtime,
                    args.repetition_id,
                    "live runtime adapter is not configured",
                )
                for task in tasks
            ]
            _emit(records, args.record_dir)
            return 2
        if args.mode == "command" and not args.agent_cmd:
            print("command mode requires --agent-cmd", file=sys.stderr)
            return 1
        command = _split_command(args.agent_cmd) if args.mode == "command" else None
        evidence = "command-adapter" if command else "offline-fixture"
        runtime = args.runtime if command else "offline-fixture"
        if not command and args.runtime != "offline-fixture":
            print("offline-fixture mode records runtime offline-fixture", file=sys.stderr)
            return 1
        records = grade_mode(
            root,
            tasks,
            condition=condition,
            runtime=runtime,
            repetition=args.repetition_id,
            grade=args.grade,
            evidence_class=evidence,
            tool_policy=args.tool_policy or evidence,
            model_version=args.model_version,
            command=command,
            timeout=args.timeout,
        )
        _emit(records, args.record_dir)
        if any(record["status"] == "BLOCKER" for record in records):
            return 2
        return 0
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except HarnessError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _print_integrity(root: Path) -> int:
    issues = check_integrity(root)
    tasks = []
    repos = set()
    if not any(issue.startswith("benchmarks/tasks") or "not valid JSON" in issue for issue in issues):
        try:
            tasks = load_tasks(root)
            repos = {task["repo"]["id"] for task in tasks if isinstance(task.get("repo"), dict)}
        except HarnessError:
            tasks = []
    if issues:
        print("MemoryCustodian benchmark integrity: FAIL")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("MemoryCustodian benchmark integrity: OK")
    print(f"Tasks: {len(tasks)}")
    print(f"Repositories: {len(repos)}")
    print(f"Conditions: {len(CONDITIONS)}")
    return 0


def _emit(records: list[dict], record_dir: str | None) -> None:
    if record_dir:
        directory = Path(record_dir)
        for record in records:
            write_result(directory, record)
    print(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True))


def _environment_record(
    root: Path,
    task: dict,
    condition: str,
    runtime: str,
    repetition: str,
    evidence_class: str,
    status: str,
    labels: list[str],
    memory_label: str | None,
    detail: str,
    checkout: Path,
) -> dict:
    return build_record(
        root=root,
        task=task,
        condition=condition,
        runtime=runtime,
        repetition=repetition,
        evidence_class=evidence_class,
        status=status,
        failure_labels=labels,
        memory_label=memory_label,
        metrics={
            "task_success": status == "PASS",
            "hard_constraint_violation": "MEMORY_AUTHORITY_VIOLATION" in labels,
            "memory_dependent_requirement_satisfied": status == "PASS",
            "stale_memory_used": "MEMORY_STALE_USE" in labels,
            "unsupported_memory_used": "MEMORY_FALSE_POSITIVE" in labels,
            "routing_complete": None,
            "context_memory_tokens": None,
            "total_input_tokens": None,
            "total_output_tokens": None,
            "wall_clock_seconds": None,
            "tool_calls": None,
            "repeated_file_reads": None,
            "tests_run": None,
            "final_test_status": None,
        },
        detail=detail,
        fixture_hash=task["repo"]["commit"],
        visible_hash=tree_hash(checkout),
        model_version="",
        tool_policy="",
    )


def _split_command(value: str) -> list[str]:
    import shlex

    parts = shlex.split(value, posix=(os.name != "nt"))
    if not parts:
        raise HarnessError("agent command is empty")
    return parts


def copy_tree(source: Path, dest: Path, skip_prefixes: tuple[str, ...]) -> None:
    for path in iter_files(source, skip_prefixes):
        relative = path.relative_to(source)
        target = dest.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _overlay_issues(
    source: Path,
    allowed_files: set[str],
    label: str,
    *,
    allow_docs: bool = False,
) -> list[str]:
    issues = []
    for path in iter_files(source, ()):
        relative = path.relative_to(source).as_posix()
        allowed = relative in allowed_files
        if allow_docs and (
            relative.startswith("docs/manual/") or relative.startswith("docs/memory/")
        ):
            allowed = True
        if not allowed:
            issues.append(f"{label}: overlay path is not allowed: {relative}")
        if ".." in Path(relative).parts:
            issues.append(f"{label}: unsafe overlay path: {relative}")
    return issues


def _remove_relative(root: Path, relative: str) -> None:
    target = _relative_target(root, relative)
    if target.is_symlink():
        raise HarnessError(f"symlink is not allowed: {relative}")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def _relative_target(root: Path, relative: str) -> Path:
    pure = Path(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise HarnessError(f"unsafe relative path: {relative}")
    return root.joinpath(*pure.parts)


def _matches_prefix(relative: str, prefix: str) -> bool:
    cleaned = prefix.strip("/")
    return relative == cleaned or relative.startswith(cleaned + "/")


def _string_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
