"""Canonical ID index and preview-only promotion operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
import re

from .conflicts import canonical_entries
from .entries import (
    StructuredEntry,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    memory_entry_ids,
    validate_evidence,
)
from .local_overlay import (
    LocalStatus,
    inspect_overlay,
    read_local_private_file,
    validated_project_identity,
)
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    iter_markdown_files,
    manifest_contract_metadata,
    parse_markdown_units,
    resolve_memory_dir,
    resolve_project_root,
)
from .subjects import load_subjects
from .plans import digest_text
from .structural import candidate_structural_operand_issues, subject_index


@dataclass(frozen=True)
class IndexedEntry:
    entry_id: str
    status: str
    scope: str
    source: str
    text: str
    structured: StructuredEntry | None = None


def _legacy_records(memory_dir: Path, *, include_archive: bool) -> list[IndexedEntry]:
    records: list[IndexedEntry] = []
    for path in iter_markdown_files(memory_dir, include_archive=include_archive):
        relative = path.relative_to(memory_dir).as_posix()
        if relative in {"manifest.md", "subjects.md", "brief.md", "reconciliations.md"} or path.name == "README.md":
            continue
        document = parse_markdown_units(path.read_text(encoding="utf-8"))
        semantic_ordinal = 0
        for unit in document.units:
            if unit.kind not in {"h2", "bullet"}:
                continue
            semantic_ordinal += 1
            if re.search(r"(?m)^## MC-(?:DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-\d{8}-[0-9a-f]{8}\b", unit.text, re.I):
                continue
            scope = (
                f"area:{Path(relative).stem}"
                if relative.startswith("areas/") else "project"
            )
            unit_ref = f"{relative}#unit-{semantic_ordinal}"
            records.append(IndexedEntry(unit_ref, "legacy", scope, relative, unit.text.strip()))
    return records


def build_index(
    project_root: Path,
    memory_dir: Path,
    *,
    include_archive: bool = False,
    include_local: bool = False,
) -> tuple[IndexedEntry, ...]:
    records = [
        IndexedEntry(
            entry.entry_id, entry.status, entry.scope,
            entry.path.relative_to(memory_dir).as_posix(), entry.text, entry,
        )
        for entry in canonical_entries(memory_dir, include_archive=include_archive)
    ]
    records.extend(_legacy_records(memory_dir, include_archive=include_archive))
    reconciliation = memory_dir / "reconciliations.md"
    if reconciliation.exists():
        text = reconciliation.read_text(encoding="utf-8")
        sections = re.split(r"(?m)(?=^## MC-REC-)", text)
        for section in sections:
            match = re.match(r"^## (MC-REC-\d{8}-[0-9a-f]{8})\b", section.strip(), re.I)
            if match:
                status = re.search(r"(?m)^Status:\s*(\S+)", section)
                records.append(IndexedEntry(match.group(1), status.group(1) if status else "", "project", "reconciliations.md", section.strip()))
    if include_local:
        overlay = inspect_overlay(
            project_root,
            validated_project_identity(memory_dir),
            shared_ids=memory_entry_ids(memory_dir),
        )
        if overlay.status == LocalStatus.REVIEW:
            detail = "; ".join(overlay.warnings) or "manual review is required"
            raise ValueError(f"Local overlay requires review before explicit indexing: {detail}")
        if overlay.status != LocalStatus.BOUND:
            raise ValueError("Local overlay is not bound to this project root.")
        if overlay.directory is None:
            raise ValueError("Local overlay review state has no safe directory.")
        from .entries import parse_structured_entries
        for path in overlay.modules:
            for entry in parse_structured_entries(path, read_local_private_file(path)):
                records.append(IndexedEntry(
                    entry.entry_id, entry.status, entry.scope,
                    f"local/{path.relative_to(overlay.directory).as_posix()}", entry.text, entry,
                ))
    by_id: dict[str, list[IndexedEntry]] = {}
    for record in records:
        by_id.setdefault(record.entry_id.casefold(), []).append(record)
    duplicates = [matches for matches in by_id.values() if len(matches) > 1]
    if duplicates:
        entry_id = duplicates[0][0].entry_id
        raise ValueError(f"Duplicate Entry ID {entry_id}; canonical lookup is unsafe.")
    return tuple(sorted(records, key=lambda item: (item.entry_id.casefold(), item.source)))


def find_entry(records: tuple[IndexedEntry, ...], entry_id: str) -> IndexedEntry:
    matches = [item for item in records if item.entry_id.casefold() == entry_id.casefold()]
    if not matches:
        raise ValueError(f"Entry ID not found: {entry_id}")
    if len(matches) != 1:
        raise ValueError(f"Duplicate Entry ID {entry_id}; canonical lookup is unsafe.")
    return matches[0]


def run_list(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    records = build_index(
        project_root, memory_dir,
        include_archive=args.include_archive,
        include_local=args.local,
    )
    records = tuple(
        item for item in records
        if (not args.status or item.status == args.status)
        and (not args.scope or item.scope == args.scope)
    )
    print("Canonical memory entries:")
    for record in records:
        print(f"- {record.entry_id} [{record.status}; {record.scope}] {record.source}")
    if not records:
        print("- none")
    return 0


def run_show(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    record = find_entry(build_index(
        project_root, memory_dir,
        include_archive=args.include_archive,
        include_local=args.local,
    ), args.entry_id)
    print(f"Source: {record.source}")
    if record.structured:
        subject_id = record.structured.fields.get("Subject") or record.structured.fields.get("Provisional-Subject")
        if subject_id:
            subjects = {item.subject_id.casefold(): item for item in load_subjects(memory_dir)}
            subject = subjects.get(subject_id.casefold())
            current = subject_id
            if subject:
                merged = re.search(r"(?m)^Merged-Into:\s*(MC-SUBJ-\S+)", subject.text)
                if merged:
                    current = merged.group(1)
            print(f"Historical Subject ID: {subject_id}")
            print(f"Current canonical Subject ID: {current}")
    print(record.text)
    return 0


def _promoted_id(candidate: IndexedEntry, kind: str) -> str:
    codes = {"decision": "DEC", "constraint": "CON", "tombstone": "DNU", "do-not-use": "DNU", "preference": "PREF"}
    digest = hashlib.sha256(f"{candidate.entry_id}\0{kind}".encode("utf-8")).hexdigest()[:8]
    return f"MC-{codes[kind]}-{date.today().strftime('%Y%m%d')}-{digest}"


def run_promote(args) -> int:
    if getattr(args, "apply", False):
        raise ValueError("Transactional promotion apply requires Protocol 0.8.")
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = (memory_dir / "manifest.md").read_text(encoding="utf-8")
    metadata = manifest_contract_metadata(manifest)
    if compare_versions(metadata["protocol_version"], CURRENT_PROTOCOL_VERSION) != 0:
        raise ValueError("Promotion preview requires Protocol 0.7.")
    records = build_index(project_root, memory_dir)
    candidate = find_entry(records, args.entry_id)
    if candidate.status != "candidate" or not candidate.structured:
        raise ValueError(f"{candidate.entry_id} is not a promotable candidate.")
    evidence = validate_evidence(args.evidence, project_root)
    if args.type in {"decision", "constraint", "tombstone", "do-not-use"} and not (
        candidate.structured.fields.get("Provisional-Subject")
        and candidate.structured.fields.get("Provisional-Facet")
    ):
        raise ValueError(
            "Hard-memory promotion preview requires candidate Provisional-Subject and Provisional-Facet."
        )
    target = {
        "decision": "decisions.md", "constraint": "constraints.md",
        "preference": "preferences.md", "tombstone": "do-not-use.md", "do-not-use": "do-not-use.md",
    }[args.type]
    if candidate.scope.startswith("area:"):
        target = f"areas/{candidate.scope.removeprefix('area:')}.md"
    new_id = _promoted_id(candidate, args.type)
    blockers: list[str] = []
    relative = candidate.source
    blockers.extend(structured_entry_schema_issues(candidate.structured, relative))
    blockers.extend(structured_entry_storage_issues(candidate.structured, relative))
    subjects = load_subjects(memory_dir)
    if args.type in {"decision", "constraint", "tombstone", "do-not-use"} or any(
        candidate.structured.fields.get(field)
        for field in ("Provisional-Subject", "Provisional-Facet")
    ):
        blockers.extend(
            f"{issue.field}: {issue.message}"
            for issue in candidate_structural_operand_issues(
                candidate.structured,
                subject_index(subjects),
            )
        )
    try:
        validate_evidence(
            candidate.structured.evidence,
            project_root,
            candidate=True,
        )
    except ValueError as exc:
        blockers.append(str(exc))
    if any(record.entry_id.casefold() == new_id.casefold() for record in records):
        blockers.append(f"Generated active Entry ID already exists: {new_id}")
    subject_id = candidate.structured.fields.get("Provisional-Subject", "")
    facet = candidate.structured.fields.get("Provisional-Facet", "")
    if subject_id and facet:
        owner_records = [
            record
            for record in records
            if record.structured
            and record.status == "active"
            and record.scope.casefold() == candidate.scope.casefold()
            and record.structured.fields.get("Subject", "").casefold() == subject_id.casefold()
            and record.structured.fields.get("Facet", "").casefold() == facet.casefold()
        ]
        if owner_records:
            blockers.append(
                "Promotion would duplicate active structural owner(s): "
                + ", ".join(sorted(record.entry_id for record in owner_records))
            )
    else:
        owner_records = []
    dependency_parts = [
        f"manifest:{digest_text(manifest)}",
        f"subjects:{digest_text((memory_dir / 'subjects.md').read_text(encoding='utf-8'))}",
        f"candidate:{candidate.source}:{digest_text(candidate.text)}",
    ]
    dependency_parts.extend(
        f"owner:{record.source}:{digest_text(record.text)}"
        for record in sorted(owner_records, key=lambda item: (item.source, item.entry_id))
    )
    plan_seed = (
        f"promote\0{metadata['project_id']}\0{candidate.entry_id}\0{new_id}\0{target}\0{'|'.join(evidence)}\0"
        + "|".join([*dependency_parts, *blockers])
    ).encode("utf-8")
    print("Promotion preview:")
    print(f"- Candidate: {candidate.entry_id} ({candidate.source})")
    print(f"- New active Entry ID: {new_id}")
    print(f"- Candidate transition: Status promoted; Promoted-To: {new_id}")
    print(f"- New entry relation: Promoted-From: {candidate.entry_id}")
    print(f"- Evidence: {', '.join(evidence)}")
    print(f"- Target files: {candidate.source}, {target}")
    if subject_id and facet:
        print(f"- Resulting structural identity: {candidate.scope}+{subject_id}+{facet}")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    print(f"Plan ID: {hashlib.sha256(plan_seed).hexdigest()[:16]}")
    print("Transactional promotion apply requires Protocol 0.8.")
    return 0
