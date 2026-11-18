"""Offline contract revisions alongside the immutable 0.13 development suite.

A revision does not replace a historical task or regrade a recorded agent run.
Its oracle, public contract, counterexamples and base materials are all pinned.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile

from benchmarks.graders.mechanical import FAILURE_LABELS, grade_script, run_visible_tests
from benchmarks.runners.harness import (
    HarnessError, SOLUTION_FILES, command_for, fixture_pin_issues, git_dirty, git_head,
    host_protocol, package_version, prepare_checkout,
    tree_hash, validate_manifest, validate_task,
)


DESCRIPTOR_KEYS = {
    "revision_format", "task_id", "task_version", "base_task_version", "reason",
    "base_task_sha256", "base_oracle_sha256", "base_reference_sha256",
    "fixture_sha256", "oracle_sha256", "public_contract_sha256", "cases_sha256",
}
SAFE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
METHOD_PATHS = (
    "benchmarks/runners/task_revisions.py", "scripts/check-benchmark-contracts.py",
    "benchmarks/runners/harness.py", "benchmarks/graders/mechanical.py",
    "benchmarks/oracles/_lib/oracle_support.py",
    "pyproject.toml", "docs/memory/manifest.md",
)


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise HarnessError("contract material must be a regular file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(pairs: list[tuple]) -> dict:
    payload = {}
    for key, value in pairs:
        if key in payload:
            raise HarnessError("duplicate revision JSON field")
        payload[key] = value
    return payload


def _constant(value: str) -> None:
    raise HarnessError("non-finite revision JSON value")


def _material(root: Path, relative: str) -> Path:
    """Reject escape paths and symlink parents before inspecting their contents."""
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise HarnessError("contract material must use a safe repository-relative path")
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise HarnessError("symlink contract material paths are not allowed")
    if not path.resolve().is_relative_to(root.resolve()):
        raise HarnessError("contract material escapes the repository")
    return path


def _json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object,
                             parse_constant=_constant)
    except (OSError, UnicodeError, ValueError) as exc:
        raise HarnessError("contract JSON is unreadable") from exc
    if not isinstance(payload, dict):
        raise HarnessError("contract JSON must be an object")
    return payload


def load_revision(root: Path, task_id: str, version: int) -> dict:
    if not isinstance(task_id, str) or not SAFE_NAME.fullmatch(task_id):
        raise HarnessError("invalid revision task ID")
    if not isinstance(version, int) or isinstance(version, bool) or version < 2:
        raise HarnessError("task revision must be an integer of at least 2")
    base_path = _material(root, f"benchmarks/tasks/{task_id}.json")
    if not base_path.is_file():
        raise HarnessError("unknown base task")
    base = _json_file(base_path)
    repo = base.get("repo")
    if (base.get("task_id") != task_id or type(base.get("task_version")) is not int
            or base["task_version"] < 1 or not isinstance(repo, dict)
            or not isinstance(repo.get("id"), str) or not SAFE_NAME.fullmatch(repo["id"])
            or repo.get("root") != f"benchmarks/fixtures/{repo['id']}"
            or base.get("success_oracle") != {"kind": "hidden-python", "script": f"benchmarks/oracles/{task_id}/check.py"}
            or not isinstance(base.get("offline_expectations"), dict)
            or base["offline_expectations"].get("reference_dir") != f"benchmarks/references/{task_id}"):
        raise HarnessError("base task identity or material paths are invalid")
    # Validate all derived parents before a validator can traverse their trees.
    _material(root, repo["root"])
    _material(root, base["success_oracle"]["script"])
    _material(root, base["offline_expectations"]["reference_dir"])
    negatives = base["offline_expectations"].get("negatives")
    if not isinstance(negatives, list):
        raise HarnessError("base task negatives must be a list")
    for negative in negatives:
        if isinstance(negative, dict) and isinstance(negative.get("dir"), str):
            _material(root, negative["dir"])
    manifest_path = _material(root, "benchmarks/benchmark-manifest.json")
    manifest = _json_file(manifest_path)
    issues = validate_manifest(manifest) + validate_task(base, root, manifest)
    if issues:
        raise HarnessError("base task no longer satisfies its original schema")
    relative = Path("benchmarks/task-revisions") / task_id / f"v{version}"
    directory = _material(root, relative.as_posix())
    path = directory / "revision.json"
    try:
        # Check the descriptor itself before reading JSON or executing any case code.
        descriptor_hash = digest(path)
        descriptor = _json_file(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise HarnessError("revision descriptor is unreadable") from exc
    if not isinstance(descriptor, dict) or set(descriptor) != DESCRIPTOR_KEYS:
        raise HarnessError("revision descriptor has unknown or missing fields")
    if (type(descriptor["revision_format"]) is not int or descriptor["revision_format"] != 1
            or descriptor["task_id"] != task_id
            or type(descriptor["task_version"]) is not int or descriptor["task_version"] != version
            or type(descriptor["base_task_version"]) is not int
            or descriptor["base_task_version"] != base["task_version"]
            or version <= base["task_version"]
            or not isinstance(descriptor["reason"], str) or not descriptor["reason"].strip()):
        raise HarnessError("revision identity or base version mismatch")
    files = {
        "base_task_sha256": base_path,
        "base_oracle_sha256": _material(root, base["success_oracle"]["script"]),
        "oracle_sha256": directory / "check.py",
        "public_contract_sha256": directory / "public-contract.md",
        "cases_sha256": directory / "cases.py",
    }
    hashes = {key: digest(value) for key, value in files.items()}
    hashes["base_reference_sha256"] = tree_hash(_material(root, base["offline_expectations"]["reference_dir"]))
    hashes["fixture_sha256"] = tree_hash(_material(root, base["repo"]["root"]))
    for key, value in hashes.items():
        if descriptor[key] != value:
            raise HarnessError(f"revision material hash mismatch: {key}")
    issues = fixture_pin_issues(root, [base])
    if issues:
        raise HarnessError("base fixture no longer matches its pinned task")
    sources = {name: digest(_material(root, name)) for name in METHOD_PATHS}
    sources[path.relative_to(root).as_posix()] = descriptor_hash
    sources.update({value.relative_to(root).as_posix(): hashes[key] for key, value in files.items()})
    return {"base_task": base, "descriptor": descriptor, "directory": directory,
            "source_sha256": sources}


def load_cases(root: Path, revision: dict) -> list[dict]:
    descriptor = revision["descriptor"]
    current = load_revision(root, descriptor["task_id"], descriptor["task_version"])
    if current["source_sha256"] != revision["source_sha256"] or current["descriptor"] != descriptor:
        raise HarnessError("contract sources changed before case execution")
    path = current["directory"] / "cases.py"
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != descriptor["cases_sha256"]:
        raise HarnessError("contract cases changed before execution")
    # Execute the bytes that were hashed, rather than reopening the file through
    # an import loader after validation.
    namespace = {"__name__": "benchmark_contract_cases", "__file__": str(path)}
    exec(compile(source, str(path), "exec"), namespace)
    cases = namespace["build_cases"](root)
    if not isinstance(cases, list) or not cases:
        raise HarnessError("contract cases must be a nonempty list")
    names = set()
    allowed_files = set(current["base_task"]["expected_touched_paths"]) & SOLUTION_FILES
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "name", "expected_status", "expected_labels", "description", "files",
        }:
            raise HarnessError("invalid contract case fields")
        name = case["name"]
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name in names:
            raise HarnessError("invalid or duplicate contract case name")
        names.add(name)
        if case["expected_status"] not in ("PASS", "FAIL"):
            raise HarnessError("contract case must expect PASS or FAIL")
        labels = case["expected_labels"]
        if (not isinstance(labels, list) or not all(isinstance(label, str) and label in FAILURE_LABELS
                                                   and label != "MEMORY_NONE" for label in labels)
                or len(set(labels)) != len(labels)
                or bool(labels) != (case["expected_status"] == "FAIL")):
            raise HarnessError("invalid contract case labels")
        if not isinstance(case["description"], str) or not case["description"]:
            raise HarnessError("contract case needs a description")
        files = case["files"]
        if (not isinstance(files, dict) or not files or set(files) - allowed_files
                or not all(isinstance(value, str) for value in files.values())):
            raise HarnessError("contract cases may change only declared supported task outputs")
    return cases


def combined_status(visible: str, oracle: str) -> str:
    if visible not in ("PASS", "FAIL") or oracle not in ("PASS", "FAIL"):
        return "BLOCKER"
    return "PASS" if visible == oracle == "PASS" else "FAIL"


def run_contracts(root: Path, revision: dict) -> list[dict]:
    base = revision["base_task"]
    version = revision["descriptor"]["task_version"]
    cases = load_cases(root, revision)
    contract = (revision["directory"] / "public-contract.md").read_text(encoding="utf-8")
    method_context = {"git_commit": git_head(root), "git_dirty": git_dirty(root)}
    records = []
    with tempfile.TemporaryDirectory(prefix="memory-custodian-contract-") as name:
        scratch = Path(name)
        for case in cases:
            grades = {}
            hashes = []
            for label, oracle in (("v1", root / base["success_oracle"]["script"]),
                                  ("v2", revision["directory"] / "check.py")):
                checkout = scratch / f"{case['name']}-{label}"
                prepare_checkout(root, base, "MEMORYCUSTODIAN", checkout)
                # New requirements are explicit in the revision's visible input.
                # These constructed cases are not historical agent checkouts.
                (checkout / "TASK-CONTRACT.md").write_text(contract, encoding="utf-8", newline="\n")
                for relative, source in case["files"].items():
                    (checkout / relative).write_text(source, encoding="utf-8", newline="\n")
                hashes.append(tree_hash(checkout))
                visible = run_visible_tests(checkout, command_for(base))
                graded = grade_script(oracle, checkout, root / "benchmarks/oracles/_lib")
                grades[label] = {"visible_tests": visible, "oracle_status": graded["status"],
                                 "status": combined_status(visible, graded["status"]),
                                 "failure_labels": graded["failure_labels"],
                                 "oracle_exit_code": graded["exit_code"]}
            if hashes[0] != hashes[1]:
                raise HarnessError("contract comparison inputs differ")
            actual = grades["v2"]
            matches = (actual["status"] == case["expected_status"]
                       and actual["oracle_status"] == case["expected_status"]
                       and actual["failure_labels"] == case["expected_labels"])
            status = "BLOCKER" if any(g["status"] == "BLOCKER" for g in grades.values()) else ("PASS" if matches else "FAIL")
            records.append({
                "contract_record_format": 1,
                "result_id": f"contract__{base['task_id']}__v{version}__{case['name']}",
                "evidence_class": "offline-contract", "status": status,
                "task_id": base["task_id"], "task_version": version,
                "package_version": package_version(root), "protocol_version": host_protocol(root),
                "case": case["name"], "description": case["description"],
                "expected_status": case["expected_status"], "expected_labels": case["expected_labels"],
                "visible_source_sha256": hashes[0], "grades": grades,
                "revision_descriptor": revision["descriptor"], "source_sha256": revision["source_sha256"],
                "method_context": method_context,
            })
    # Verify every pinned source again before publishing any record.
    current = load_revision(root, base["task_id"], version)
    if current["source_sha256"] != revision["source_sha256"]:
        raise HarnessError("contract sources changed during execution")
    return records


def markdown_report(records: list[dict]) -> str:
    if not records:
        raise HarnessError("cannot report an empty contract run")
    first = records[0]
    lines = [f"# {first['task_id']} v{first['task_version']} contract validation", "",
             f"Generated: {datetime.now(timezone.utc).isoformat()}",
             f"Task: `{first['task_id']}`, revision `{first['task_version']}`.", "",
             "Constructed offline cases only; no live-agent, effectiveness, or checkpoint claim.", "",
             "| Case | Expected | v1 oracle | v2 oracle | Contract check |",
             "| --- | --- | --- | --- | --- |"]
    for row in records:
        lines.append("| " + " | ".join([row["case"], row["expected_status"],
                     row["grades"]["v1"]["oracle_status"], row["grades"]["v2"]["oracle_status"], row["status"]]) + " |")
    false_rejects = sum(row["expected_status"] == "PASS" and row["grades"]["v1"]["oracle_status"] == "FAIL" for row in records)
    false_accepts = sum(row["expected_status"] == "FAIL" and row["grades"]["v1"]["oracle_status"] == "PASS" for row in records)
    lines += ["", f"Contract checks passed: {sum(row['status'] == 'PASS' for row in records)}/{len(records)}.",
              f"The v1 oracle rejected {false_rejects} positive examples and accepted {false_accepts} negative examples in this constructed set.",
              "", "## Scope and interpretation", "",
              "The task revision's public-contract.md is visible as TASK-CONTRACT.md in every constructed checkout.",
              "Acceptance follows that explicit task contract, with positive and negative controls for behavior and supported syntax.",
              "These finite development checks are not an adversarial anti-cheating guarantee or a general natural-language evaluator.",
              "This development revision is informed by the pilot outcomes and cannot be treated as held-out evidence.",
              "The old task, fixture, reference, v1 oracle, frozen runtime methods, and historical result records remain unchanged.",
              "These are newly constructed examples, not regrading of discarded agent workspaces; historical scores are not revised.",
              "Oracle weaknesses alone do not establish that an actual historical agent output was correct or that production Skill/CLI behavior is defective.",
              "", "## Provenance and reproduction", "",
              "Each record pins the base task, fixture, v1 oracle/reference, v2 descriptor/oracle/public contract/cases, and method sources.",
              "The two graders receive separate checkouts with identical input hashes. Infrastructure failures stay BLOCKER.",
              "Records use exclusive creation and a directory separate from the historical pilots.", "",
              "Each record retains method source hashes and Git context. A later validator implementation may differ; historical records are not overwritten.", "",
              "```bash", "python3 scripts/check-benchmark-contracts.py \\",
              f"  --task {first['task_id']} --task-version {first['task_version']}", "```", ""]
    return "\n".join(lines)
