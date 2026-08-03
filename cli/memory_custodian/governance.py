"""Read-only Protocol 0.7 relation and reconciliation previews."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .conflicts import canonical_entries
from .entries import ENTRY_ID_RE, StructuredEntry, validate_evidence
from .plans import digest_text
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    protocol_contract_metadata,
    project_id_from_manifest,
    read_text,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
from .reconciliations import (
    RESOLUTIONS,
    ReconciliationRecord,
    parse_reconciliations,
    validate_reconciliations,
)
from .structural import active_structural_operand_issues, subject_index
from .subjects import Subject, load_subjects


@dataclass(frozen=True)
class GovernanceProject:
    project_root: Path
    memory_dir: Path
    project_id: str
    manifest_sha256: str


def _project(args) -> GovernanceProject:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = read_text(memory_dir / "manifest.md")
    metadata = protocol_contract_metadata(manifest)
    version = metadata["protocol_version"]
    comparison = compare_versions(version, CURRENT_PROTOCOL_VERSION)
    if comparison is None:
        raise ValueError(f"Invalid protocol version {version!r} in manifest.md.")
    if comparison < 0:
        raise ValueError(
            f"Governance preview requires Protocol {CURRENT_PROTOCOL_VERSION}; "
            f"project uses {version}. Run `memory-custodian migrate`."
        )
    if comparison > 0:
        raise ValueError(
            f"Project protocol {version} is newer than this CLI supports "
            f"({CURRENT_PROTOCOL_VERSION}); update MemoryCustodian."
        )
    if not (memory_dir / "subjects.md").is_file():
        raise ValueError(
            "Governance preview requires the declared subjects.md registry; "
            "run `memory-custodian init --repair`."
        )
    project_id = project_id_from_manifest(manifest)
    if not project_id:
        raise ValueError(
            "Governance preview requires manifest project_id metadata; "
            "run `memory-custodian migrate`."
        )
    return GovernanceProject(
        project_root,
        memory_dir,
        project_id,
        digest_text(manifest),
    )


def _entry(entries: tuple[StructuredEntry, ...], entry_id: str) -> StructuredEntry:
    matches = [item for item in entries if item.entry_id.casefold() == entry_id.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Entry ID must resolve exactly once: {entry_id}")
    return matches[0]


def _plan_id(command: str, project_id: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"command": command, "project_id": project_id, **payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _entry_state(entry: StructuredEntry, memory_dir: Path) -> dict[str, str]:
    return {
        "entry_id": entry.entry_id,
        "path": entry.path.relative_to(memory_dir).as_posix(),
        "text_sha256": digest_text(entry.text),
    }


def _exception_relation_blockers(
    area: StructuredEntry,
    baseline: StructuredEntry,
    subjects: dict[str, tuple[Subject, ...]],
) -> list[str]:
    blockers = [
        f"{label} {issue.field}: {issue.message}"
        for label, entry in (("Source", area), ("Target", baseline))
        for issue in active_structural_operand_issues(entry, subjects)
    ]
    if not area.scope.startswith("area:"):
        blockers.append("Exception source must be area-scoped.")
    if baseline.scope != "project":
        blockers.append("Exception target must be project-scoped.")
    for field in ("Subject", "Facet"):
        if area.fields.get(field, "").casefold() != baseline.fields.get(field, "").casefold():
            blockers.append(f"Source and target must have the same {field}.")
    if baseline.fields.get("Exception-To"):
        blockers.append("Exception target must not itself declare Exception-To.")
    return blockers


def _exception_add(args) -> int:
    project = _project(args)
    memory_dir = project.memory_dir
    entries = canonical_entries(memory_dir)
    subjects_path = memory_dir / "subjects.md"
    subjects = subject_index(load_subjects(memory_dir))
    area = _entry(entries, args.entry_id)
    baseline = _entry(entries, args.target_entry_id)
    blockers = _exception_relation_blockers(area, baseline, subjects)
    current = area.fields.get("Exception-To", "")
    if current and current.casefold() != baseline.entry_id.casefold():
        blockers.append(f"Source already has Exception-To: {current}.")
    blockers = list(dict.fromkeys(blockers))

    payload = {
        "source": area.entry_id,
        "target": baseline.entry_id,
        "dependencies": [
            _entry_state(area, memory_dir), _entry_state(baseline, memory_dir),
        ],
        "manifest_sha256": project.manifest_sha256,
        "subjects_sha256": digest_text(read_text(subjects_path)),
        "blockers": sorted(blockers),
    }
    print("Exception-To add preview:")
    print(
        f"Source: {area.entry_id} "
        f"({area.path.relative_to(memory_dir).as_posix()}; {area.scope}; {area.status})"
    )
    print(
        f"Target: {baseline.entry_id} "
        f"({baseline.path.relative_to(memory_dir).as_posix()}; {baseline.scope}; {baseline.status})"
    )
    print(
        f"Structural identity: "
        f"{area.fields.get('Subject', '-')}+{area.fields.get('Facet', '-')}"
    )
    print(f"Proposed relation: Exception-To: {baseline.entry_id}")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    print(f"Plan ID: {_plan_id('exception add', project.project_id, payload)}")
    print("Transactional Exception-To apply requires Protocol 0.8.")
    return 0


def _exception_remove(args) -> int:
    project = _project(args)
    memory_dir = project.memory_dir
    entries = canonical_entries(memory_dir)
    subjects_path = memory_dir / "subjects.md"
    subjects = subject_index(load_subjects(memory_dir))
    area = _entry(entries, args.entry_id)
    current = area.fields.get("Exception-To", "")
    targets = [item for item in entries if item.entry_id.casefold() == current.casefold()]
    if len(targets) == 1:
        blockers = _exception_relation_blockers(area, targets[0], subjects)
    else:
        blockers = [
            f"Source {issue.field}: {issue.message}"
            for issue in active_structural_operand_issues(area, subjects)
        ]
        if not area.scope.startswith("area:"):
            blockers.append("Exception source must be area-scoped.")
        blockers.append(
            "Source does not have an Exception-To relation."
            if not current else "Exception-To target must resolve exactly once."
        )
    blockers = list(dict.fromkeys(blockers))
    target_label = current or "none"
    resulting_review = len(targets) == 1 and not blockers
    payload = {
        "source": area.entry_id,
        "current_target": current,
        "dependencies": [
            _entry_state(entry, memory_dir) for entry in (area, *targets)
        ],
        "manifest_sha256": project.manifest_sha256,
        "subjects_sha256": digest_text(read_text(subjects_path)),
        "blockers": sorted(blockers),
        "resulting_review": resulting_review,
    }
    print("Exception-To remove preview:")
    print(
        f"Source: {area.entry_id} "
        f"({area.path.relative_to(memory_dir).as_posix()}; {area.scope}; {area.status})"
    )
    print(f"Current relation target: {target_label}")
    print(f"Proposed relation: remove Exception-To: {target_label}")
    print("Resulting review:")
    print(
        "- MC-CONFLICT-002 project/area overlap will require review."
        if resulting_review else "- result not established due to blockers."
    )
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    print(f"Plan ID: {_plan_id('exception remove', project.project_id, payload)}")
    print("Transactional Exception-To apply requires Protocol 0.8.")
    return 0


def _reconcile_preview(args) -> int:
    project = _project(args)
    project_root = project.project_root
    memory_dir = project.memory_dir
    normalized_entries: dict[str, str] = {}
    for value in args.entry:
        candidate = value.strip().upper()
        if ENTRY_ID_RE.fullmatch(candidate) is None:
            raise ValueError(f"Invalid reconciliation Entry ID: {value}")
        normalized_entries.setdefault(candidate.casefold(), candidate)
    requested = tuple(sorted(normalized_entries.values(), key=str.casefold))
    if len(requested) < 2:
        raise ValueError("Reconciliation preview requires at least two distinct --entry values.")
    evidence = tuple(sorted(dict.fromkeys(
        validate_evidence(args.evidence, project_root)
    ), key=str.casefold))
    title = " ".join(args.title.split())
    if not title:
        raise ValueError("Reconciliation title must not be empty.")
    record_seed = "\0".join([
        project.project_id, args.resolution, title, *requested, *evidence,
    ])
    suffix = hashlib.sha256(record_seed.encode()).hexdigest()[:8]
    record_id = f"MC-REC-{today().replace('-', '')}-{suffix}"
    unit = (
        f"## {record_id} — {title}\n\n"
        "Status: active\nEntries:\n"
        + "\n".join(f"- {value}" for value in requested)
        + f"\nResolution: {args.resolution}\nEvidence:\n"
        + "\n".join(f"- {value}" for value in evidence)
    )
    proposed = ReconciliationRecord(
        record_id, title, "active", args.resolution, requested, evidence, unit,
    )
    path = memory_dir / "reconciliations.md"
    existing, parse_issues = (
        parse_reconciliations(path, read_text(path)) if path.exists() else ((), ())
    )
    entries = canonical_entries(memory_dir)
    _valid, issues = validate_reconciliations(
        (*existing, proposed), parse_issues, entries, load_subjects(memory_dir),
    )
    blockers = [
        (f"{issue.record_id}: " if issue.record_id else "") + issue.message
        for issue in issues
    ]
    payload = {
        "record": unit,
        "base_sha256": digest_text(read_text(path) if path.exists() else ""),
        "entry_dependencies": [
            _entry_state(entry, memory_dir)
            for entry in sorted(
                entries,
                key=lambda item: (
                    item.entry_id.casefold(), item.path.as_posix(), digest_text(item.text),
                ),
            )
        ],
        "manifest_sha256": project.manifest_sha256,
        "subjects_sha256": digest_text(read_text(memory_dir / "subjects.md")),
        "blockers": blockers,
    }
    print("Reconciliation record preview:")
    print(unit)
    print("Inventory:")
    for value in requested:
        matches = [entry for entry in entries if entry.entry_id.casefold() == value.casefold()]
        if len(matches) == 1:
            entry = matches[0]
            print(
                f"- {entry.entry_id} "
                f"({entry.path.relative_to(memory_dir).as_posix()}; {entry.scope}; {entry.status})"
            )
        else:
            print(f"- {value} (resolves {len(matches)} times)")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    print(f"Plan ID: {_plan_id('reconcile preview', project.project_id, payload)}")
    print("Transactional reconciliation apply requires Protocol 0.8.")
    return 0


def run(args) -> int:
    if args.command == "exception":
        return {"add": _exception_add, "remove": _exception_remove}[args.exception_command](args)
    return _reconcile_preview(args)


__all__ = ["RESOLUTIONS", "run"]
