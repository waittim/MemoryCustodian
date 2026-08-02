"""Read-only Protocol 0.7 relation and reconciliation previews."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .conflicts import canonical_entries
from .entries import ENTRY_ID_RE, StructuredEntry, validate_evidence
from .plans import digest_text
from .protocol import (
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
from .subjects import load_subjects


def _project(args) -> tuple[Path, Path, str]:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    project_id = project_id_from_manifest(read_text(memory_dir / "manifest.md"))
    if not project_id:
        raise ValueError("Protocol 0.7 governance preview requires manifest project_id metadata.")
    return project_root, memory_dir, project_id


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


def _exception_add(args) -> int:
    _project_root, memory_dir, project_id = _project(args)
    entries = canonical_entries(memory_dir)
    area = _entry(entries, args.entry_id)
    baseline = _entry(entries, args.target_entry_id)
    blockers: list[str] = []
    if area.status != "active" or not area.scope.startswith("area:"):
        blockers.append("Exception source must be an active area-scoped entry.")
    if baseline.status != "active" or baseline.scope != "project":
        blockers.append("Exception target must be an active project-scoped entry.")
    for field in ("Subject", "Facet"):
        if (
            not area.fields.get(field)
            or area.fields.get(field, "").casefold()
            != baseline.fields.get(field, "").casefold()
        ):
            blockers.append(f"Source and target must have the same {field}.")
    current = area.fields.get("Exception-To", "")
    if current and current.casefold() != baseline.entry_id.casefold():
        blockers.append(f"Source already has Exception-To: {current}.")

    payload = {
        "source": area.entry_id,
        "target": baseline.entry_id,
        "source_sha256": digest_text(area.text),
        "target_sha256": digest_text(baseline.text),
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
    print(f"Plan ID: {_plan_id('exception add', project_id, payload)}")
    print("Transactional Exception-To apply requires Protocol 0.8.")
    return 0


def _exception_remove(args) -> int:
    _project_root, memory_dir, project_id = _project(args)
    entries = canonical_entries(memory_dir)
    area = _entry(entries, args.entry_id)
    current = area.fields.get("Exception-To", "")
    blockers: list[str] = []
    if area.status != "active" or not area.scope.startswith("area:"):
        blockers.append("Exception source must be an active area-scoped entry.")
    if not current:
        blockers.append("Source does not have an Exception-To relation.")
    targets = [item for item in entries if item.entry_id.casefold() == current.casefold()]
    target_label = current or "none"
    resulting_review = bool(
        len(targets) == 1
        and targets[0].status == "active"
        and targets[0].scope == "project"
        and targets[0].fields.get("Subject", "").casefold() == area.fields.get("Subject", "").casefold()
        and targets[0].fields.get("Facet", "").casefold() == area.fields.get("Facet", "").casefold()
    )
    payload = {
        "source": area.entry_id,
        "current_target": current,
        "source_sha256": digest_text(area.text),
        "blockers": sorted(blockers),
    }
    print("Exception-To remove preview:")
    print(
        f"Source: {area.entry_id} "
        f"({area.path.relative_to(memory_dir).as_posix()}; {area.scope}; {area.status})"
    )
    print(f"Current relation target: {target_label}")
    print(f"Proposed relation: remove Exception-To: {target_label}")
    print("Resulting review:")
    print("- MC-CONFLICT-002 project/area overlap will require review." if resulting_review else "- none established")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    print(f"Plan ID: {_plan_id('exception remove', project_id, payload)}")
    print("Transactional Exception-To apply requires Protocol 0.8.")
    return 0


def _reconcile_preview(args) -> int:
    project_root, memory_dir, project_id = _project(args)
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
    record_seed = "\0".join([project_id, args.resolution, title, *requested, *evidence])
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
    print(f"Plan ID: {_plan_id('reconcile preview', project_id, payload)}")
    print("Transactional reconciliation apply requires Protocol 0.8.")
    return 0


def run(args) -> int:
    if args.command == "exception":
        return {"add": _exception_add, "remove": _exception_remove}[args.exception_command](args)
    return _reconcile_preview(args)


__all__ = ["RESOLUTIONS", "run"]
