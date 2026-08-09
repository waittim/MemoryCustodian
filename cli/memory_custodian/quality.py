"""Protocol 0.7 routing, reachability, and freshness checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .conflicts import analyze_conflicts, canonical_entries
from .protocol import (
    manifest_contract_metadata,
    parse_manifest_task_file_specs,
    protocol_metadata,
    protocol_contract_metadata,
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
    manifest = manifest_path.read_text(encoding="utf-8")
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
    manifest = (memory_dir / "manifest.md").read_text(encoding="utf-8")
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
    return tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.message)))


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
            manifest_path.read_text(encoding="utf-8"),
            allow_missing_section=True,
        )
    except ValueError as exc:
        return (QualityFinding("ERROR", "MC-ROUTING-007", str(exc)),)
    findings: list[QualityFinding] = []
    head = _head_revision(project_root)
    saw_revision = False
    entries = canonical_entries(memory_dir)
    by_id = {
        entry.entry_id.casefold(): entry
        for entry in canonical_entries(memory_dir, include_archive=True)
    }
    for entry in entries:
        if entry.status in {"active", "candidate"}:
            for evidence in entry.evidence:
                prefix, separator, rest = evidence.partition(":")
                if not separator or prefix not in {"repo", "doc", "test"}:
                    continue
                raw_path, at, revision = rest.partition("@")
                if not (project_root / raw_path).exists():
                    findings.append(QualityFinding(
                        "ERROR", "MC-FRESH-001",
                        f"{entry.entry_id} Evidence path does not exist: {prefix}:{raw_path}",
                    ))
                if at:
                    saw_revision = True
                    if head is not None and not head.startswith(revision) and not revision.startswith(head):
                        findings.append(QualityFinding(
                            "WARNING", "MC-FRESH-002",
                            f"{entry.entry_id} Evidence revision differs from current Git HEAD.",
                        ))
        for relation in ("Supersedes", "Superseded-By", "Promoted-From", "Promoted-To", "Exception-To"):
            target = entry.fields.get(relation)
            if target and target.casefold() not in by_id:
                findings.append(QualityFinding(
                    "ERROR", "MC-FRESH-004",
                    f"{entry.entry_id} {relation} references missing entry {target}.",
                ))
    from .subjects import load_subjects
    subjects = {item.subject_id.casefold(): item for item in load_subjects(memory_dir)}
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
        if conflict.code == "MC-CONFLICT-008" and "reconciliation" in conflict.message.casefold():
            findings.append(QualityFinding(
                "ERROR", "MC-FRESH-006", conflict.message,
            ))
    if saw_revision and head is None:
        findings.append(QualityFinding(
            "INFO", "MC-FRESH-003",
            "Git is unavailable; revision-backed Evidence was not freshness-checked.",
        ))
    return tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.message)))


def render_quality(title: str, findings: tuple[QualityFinding, ...]) -> int:
    status = "OK" if not any(item.severity == "ERROR" for item in findings) else "FAILED"
    print(f"MemoryCustodian {title}: {status}")
    if not findings:
        print("- no findings")
    for finding in findings:
        print(f"- {finding.code} {finding.severity}: {finding.message}")
    return 1 if any(item.severity == "ERROR" for item in findings) else 0
