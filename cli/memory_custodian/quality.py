"""Protocol 0.7 routing, reachability, and freshness checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .conflicts import analyze_conflicts, canonical_entries
from .entries import parse_structured_entries, structured_relation_issues, validate_evidence
from .protocol import (
    manifest_contract_metadata,
    canonical_memory_files,
    managed_markdown_files,
    parse_manifest_task_file_specs,
    protocol_metadata,
    protocol_contract_metadata,
    read_managed_text,
    validate_manifest_routes,
)
from .routes import CANONICAL_TASKS, SUBSTANTIAL_TASKS, parse_optional_module_index


@dataclass(frozen=True)
class QualityFinding:
    severity: str
    code: str
    message: str


def routing_findings(memory_dir: Path) -> tuple[QualityFinding, ...]:
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        return (QualityFinding("ERROR", "MC-ROUTING-001", "manifest.md is missing."),)
    manifest = read_managed_text(memory_dir, manifest_path)
    findings = [
        QualityFinding("ERROR", "MC-ROUTING-002", issue)
        for issue in validate_manifest_routes(manifest)
    ]
    try:
        metadata = protocol_contract_metadata(manifest, allow_missing_section=True)
    except ValueError as exc:
        metadata = protocol_metadata(manifest)
        findings.append(QualityFinding("ERROR", "MC-ROUTING-007", str(exc)))
    version = metadata.get("protocol_version", "0.5")
    try:
        declarations = parse_optional_module_index(manifest, legacy_compatible=version != "0.7")
    except ValueError as exc:
        declarations = ()
        findings.append(QualityFinding("ERROR", "MC-ROUTING-003", str(exc)))
    for task in sorted(SUBSTANTIAL_TASKS):
        try:
            specs = parse_manifest_task_file_specs(manifest, task)
            paths = {path for path, _required in specs}
        except ValueError:
            continue
        for relative, required in specs:
            if required and not (memory_dir / relative).exists():
                findings.append(QualityFinding(
                    "ERROR", "MC-ROUTING-006",
                    f"Required module is missing for {task}: {relative}",
                ))
        if "constraints.md" not in paths:
            findings.append(QualityFinding(
                "WARNING", "MC-ROUTING-004",
                f"Routing safety review required: {task} does not reach root constraints.md.",
            ))
    for declaration in declarations:
        path = memory_dir / declaration.module_id
        if not path.exists():
            findings.append(QualityFinding(
                "WARNING", "MC-ROUTING-005",
                f"Enabled optional module is missing: {declaration.module_id}",
            ))
    return tuple(sorted(set(findings), key=lambda item: (item.severity, item.code, item.message)))


def reachability_findings(memory_dir: Path) -> tuple[QualityFinding, ...]:
    manifest = read_managed_text(memory_dir, memory_dir / "manifest.md")
    try:
        metadata = manifest_contract_metadata(
            manifest,
            allow_missing_section=True,
        )
    except ValueError as exc:
        return (QualityFinding("ERROR", "MC-ROUTING-007", str(exc)),)
    version = metadata.get("protocol_version", "0.5")
    declarations = parse_optional_module_index(manifest, legacy_compatible=version != "0.7")
    reachable: set[str] = set()
    for task in CANONICAL_TASKS:
        try:
            reachable.update(path for path, _required in parse_manifest_task_file_specs(manifest, task))
        except ValueError:
            pass
    reachable.update(item.module_id for item in declarations)
    declarations_by_path = {item.module_id: item for item in declarations}
    findings: list[QualityFinding] = []
    canonical_paths = set(canonical_memory_files(memory_dir))
    for path in managed_markdown_files(memory_dir):
        if path in canonical_paths or path.name.casefold() == "readme.md":
            continue
        if path.relative_to(memory_dir).as_posix().startswith("archive/"):
            continue
        for entry in parse_structured_entries(path, read_managed_text(memory_dir, path)):
            if entry.status == "active":
                findings.append(QualityFinding(
                    "ERROR", "MC-REACH-001",
                    f"{entry.entry_id} in {path.relative_to(memory_dir).as_posix()} "
                    "is outside canonical manifest-authorized storage.",
                ))
    for entry in canonical_entries(memory_dir):
        if entry.status != "active":
            continue
        relative = entry.path.relative_to(memory_dir).as_posix()
        if relative not in reachable:
            hard = entry.entry_id.split("-", 2)[1].upper() in {"CON", "DNU", "TOMB"}
            severity = "ERROR" if hard and entry.scope == "project" else "WARNING"
            findings.append(QualityFinding(
                severity, "MC-REACH-001",
                f"{entry.entry_id} in {relative} is unreachable from normal routes.",
            ))
        if entry.scope.startswith("area:") and entry.entry_id.split("-", 2)[1].upper() == "CON":
            declaration = declarations_by_path.get(relative)
            if declaration is None or declaration.activation not in {"path", "path-or-explicit", "explicit-only"}:
                findings.append(QualityFinding(
                    "ERROR", "MC-REACH-002",
                    f"Area constraint {entry.entry_id} has no valid path or explicit activation.",
                ))
    unique = {
        (item.severity, item.code, item.message): item
        for item in findings
    }
    return tuple(sorted(unique.values(), key=lambda item: (item.severity, item.code, item.message)))


def _head_revision(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root,
            text=True, capture_output=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def freshness_findings(project_root: Path, memory_dir: Path) -> tuple[QualityFinding, ...]:
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        return (QualityFinding("ERROR", "MC-ROUTING-007", "manifest.md is missing."),)
    try:
        manifest_contract_metadata(
            read_managed_text(memory_dir, manifest_path),
            allow_missing_section=True,
        )
    except ValueError as exc:
        return (QualityFinding("ERROR", "MC-ROUTING-007", str(exc)),)
    findings: list[QualityFinding] = []
    head = _head_revision(project_root)
    saw_revision = False
    entries = canonical_entries(memory_dir)
    all_entries = canonical_entries(memory_dir, include_archive=True)
    from .subjects import load_subjects
    subject_records = load_subjects(memory_dir)
    subjects = {item.subject_id.casefold(): item for item in subject_records}

    def check_evidence(owner: str, evidence: tuple[str, ...]) -> None:
        nonlocal saw_revision
        for value in evidence:
            prefix, separator, rest = value.partition(":")
            if not separator or prefix not in {"repo", "doc", "test"}:
                continue
            try:
                # Validate the path syntax and containment even when the
                # registry's structural pass allowed a missing source.
                normalized_evidence = validate_evidence(
                    (value,), project_root, allow_missing=True,
                )[0]
            except ValueError:
                findings.append(QualityFinding(
                    "ERROR", "MC-FRESH-001",
                    f"{owner} Evidence has an unsafe or invalid source path.",
                ))
                continue
            # validate_evidence canonicalizes path separators before checking
            # the filesystem.  Use that same canonical value for freshness;
            # otherwise a valid Windows-style relative path is checked under
            # its literal POSIX backslash spelling and is falsely reported as
            # missing.
            prefix, separator, rest = normalized_evidence.partition(":")
            raw_path, at, revision = rest.partition("@")
            target = (project_root / raw_path).resolve()
            try:
                target.relative_to(project_root.resolve())
            except ValueError:
                # This is normally covered above; retain a defensive check so
                # freshness never follows an escaping Evidence path.
                findings.append(QualityFinding(
                    "ERROR", "MC-FRESH-001",
                    f"{owner} Evidence path escapes the project: {prefix}:{raw_path}",
                ))
                continue
            if not target.exists():
                findings.append(QualityFinding(
                    "ERROR", "MC-FRESH-001",
                    f"{owner} Evidence path does not exist: {prefix}:{raw_path}",
                ))
            if at:
                saw_revision = True
                if head is not None and not head.startswith(revision) and not revision.startswith(head):
                    findings.append(QualityFinding(
                        "WARNING", "MC-FRESH-002",
                        f"{owner} Evidence revision differs from current Git HEAD.",
                    ))

    for entry in entries:
        if entry.status in {"active", "candidate"}:
            check_evidence(entry.entry_id, entry.evidence)
    for subject in subject_records:
        check_evidence(f"Subject {subject.subject_id}", subject.evidence)
    findings.extend(
        QualityFinding("ERROR", "MC-FRESH-004", issue + ".")
        for issue in structured_relation_issues(
            all_entries,
            merged_subject_ids={
                item.subject_id for item in subjects.values() if item.status == "merged"
            },
        )
    )
    for subject in subjects.values():
        if subject.status == "merged" and (
            not subject.merged_into
            or subject.merged_into.casefold() not in subjects
            or subjects[subject.merged_into.casefold()].status != "active"
        ):
            findings.append(QualityFinding(
                "ERROR", "MC-FRESH-005",
                f"{subject.subject_id} has a broken Merged-Into relation.",
            ))
    for conflict in analyze_conflicts(memory_dir).findings:
        freshness_code = {
            "MC-CONFLICT-005": "MC-FRESH-005",
            "MC-CONFLICT-006": "MC-FRESH-004",
            "MC-CONFLICT-007": "MC-FRESH-004",
        }.get(conflict.code)
        if conflict.code == "MC-CONFLICT-008" and "reconciliation" in conflict.message.casefold():
            freshness_code = "MC-FRESH-006"
        if freshness_code:
            findings.append(QualityFinding(
                "ERROR", freshness_code, conflict.message,
            ))
    if saw_revision and head is None:
        findings.append(QualityFinding(
            "INFO", "MC-FRESH-003",
            "Git is unavailable; revision-backed Evidence was not freshness-checked.",
        ))
    unique = {
        (item.severity, item.code, item.message): item
        for item in findings
    }
    return tuple(sorted(unique.values(), key=lambda item: (item.severity, item.code, item.message)))


def render_quality(title: str, findings: tuple[QualityFinding, ...]) -> int:
    status = "OK" if not any(item.severity == "ERROR" for item in findings) else "FAILED"
    print(f"MemoryCustodian {title}: {status}")
    if not findings:
        print("- no findings")
    for finding in findings:
        print(f"- {finding.code} {finding.severity}: {finding.message}")
    return 1 if any(item.severity == "ERROR" for item in findings) else 0
