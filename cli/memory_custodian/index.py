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
    heading_entry_ids,
    parse_structured_entries,
    render_active_entry,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    structured_relation_issues,
    memory_entry_ids,
    validate_evidence,
    validate_scope,
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
    manifest_with_optional_module_index,
    parse_markdown_units,
    resolve_memory_dir,
    resolve_project_root,
    read_managed_text,
)
from .subjects import load_subjects, validate_subject_registry
from .plans import digest_text
from .structural import (
    active_structural_operand_issues,
    candidate_structural_operand_issues,
    subject_index,
)


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
        if relative in {"manifest.md", "subjects.md", "brief.md", "reconciliations.md"} or path.name.casefold() == "readme.md":
            continue
        document = parse_markdown_units(read_managed_text(memory_dir, path))
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
    relation_entries = canonical_entries(memory_dir, include_archive=True)
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
        from .reconciliations import parse_reconciliations, validate_reconciliations

        text = read_managed_text(memory_dir, reconciliation)
        reconciliation_records, parse_issues = parse_reconciliations(
            reconciliation, text, project_root, include_invalid=True
        )
        valid_records, validation_issues = validate_reconciliations(
            reconciliation_records,
            parse_issues,
            relation_entries,
            tuple(load_subjects(memory_dir)),
        )
        valid_ids = {record.record_id.casefold() for record in valid_records}
        invalid_ids = {
            issue.record_id.casefold()
            for issue in validation_issues
            if issue.record_id
        }
        records.extend(
            IndexedEntry(
                record.record_id,
                record.status if record.record_id.casefold() in valid_ids else "INVALID",
                "project",
                "reconciliations.md",
                record.text,
            )
            for record in reconciliation_records
            if record.record_id.casefold() in valid_ids | invalid_ids
        )
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
            if subject and subject.status == "merged" and subject.merged_into:
                current = subject.merged_into
            print(f"Historical Subject ID: {subject_id}")
            print(f"Current canonical Subject ID: {current}")
    # The parser owns the body envelope boundary.  Show its semantic source,
    # not the explicit serialization wrapper; user-authored ``&#8283;`` text
    # remains untouched because it has no protocol meaning.
    print(
        (record.structured.display_text or record.text)
        if record.structured else record.text
    )
    return 0


def _promoted_id(candidate: IndexedEntry, kind: str) -> str:
    codes = {
        "decision": "DEC", "constraint": "CON", "tombstone": "DNU",
        "do-not-use": "DNU", "preference": "PREF", "area": "AREA",
    }
    digest = hashlib.sha256(f"{candidate.entry_id}\0{kind}".encode("utf-8")).hexdigest()[:8]
    return f"MC-{codes[kind]}-{date.today().strftime('%Y%m%d')}-{digest}"


def run_promote(args) -> int:
    if getattr(args, "apply", False):
        raise ValueError("Transactional promotion apply requires Protocol 0.8.")
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = read_managed_text(memory_dir, memory_dir / "manifest.md")
    metadata = manifest_contract_metadata(manifest)
    if compare_versions(metadata["protocol_version"], CURRENT_PROTOCOL_VERSION) != 0:
        raise ValueError("Promotion preview requires Protocol 0.7.")
    registry_issues = validate_subject_registry(memory_dir, project_root)
    if registry_issues:
        raise ValueError("Subject registry is invalid: " + "; ".join(registry_issues[:5]))
    records = build_index(project_root, memory_dir)
    candidate = find_entry(records, args.entry_id)
    if candidate.status != "candidate" or not candidate.structured:
        raise ValueError(f"{candidate.entry_id} is not a promotable candidate.")
    scope = validate_scope(candidate.scope)
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
    if scope.startswith("area:"):
        target = f"areas/{scope.removeprefix('area:')}.md"
    active_kind = (
        "area" if scope.startswith("area:") and args.type == "decision" else args.type
    )
    target_path = memory_dir.joinpath(*Path(target).parts)
    try:
        target_path.resolve().relative_to(memory_dir.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("Promotion target escapes the managed memory directory.") from exc
    new_id = _promoted_id(candidate, active_kind)
    blockers: list[str] = []
    shared_ids = memory_entry_ids(memory_dir)
    try:
        overlay = inspect_overlay(
            project_root,
            metadata["project_id"],
            shared_ids=shared_ids,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        overlay = None
        blockers.append(f"Local overlay could not be inspected safely: {exc}")
    local_ids: set[str] = set()
    local_dependencies: list[str] = []
    if overlay is not None:
        local_dependencies.append(f"status:{overlay.status.value}")
        local_dependencies.extend(
            f"warning:{warning}" for warning in overlay.warnings
        )
        if overlay.status == LocalStatus.REVIEW:
            detail = "; ".join(overlay.warnings) or "manual review is required"
            blockers.append(f"Local overlay requires review: {detail}")
        if overlay.directory is not None:
            for module in overlay.modules:
                try:
                    local_text = read_local_private_file(module)
                    module_ids = heading_entry_ids(local_text)
                except (OSError, RuntimeError, ValueError) as exc:
                    blockers.append(
                        f"Local overlay module {module.name} could not be inspected safely: {exc}"
                    )
                    continue
                local_ids.update(module_ids)
                relative_module = module.relative_to(overlay.directory).as_posix()
                local_dependencies.append(
                    f"module:{relative_module}:ids={','.join(sorted(item.casefold() for item in module_ids))}:"
                    f"{digest_text(local_text)}"
                )
    if new_id.casefold() in {item.casefold() for item in local_ids}:
        blockers.append(
            f"Generated active Entry ID already exists in the bound local overlay: {new_id}"
        )
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
    candidate_type = candidate.structured.fields.get("Candidate-Type", "").casefold()
    requested_type = "tombstone" if args.type == "do-not-use" else args.type
    declared_type = "tombstone" if candidate_type == "do-not-use" else candidate_type
    if declared_type != requested_type:
        blockers.append(
            f"Candidate-Type {candidate_type!r} does not match requested promotion type {args.type!r}"
        )
    if new_id.casefold() in {entry_id.casefold() for entry_id in memory_entry_ids(memory_dir)}:
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
    target_exists = target_path.exists()
    target_baseline = read_managed_text(memory_dir, target_path) if target_exists else ""
    updated_manifest, manifest_changed = manifest_with_optional_module_index(manifest, target)

    promoted_candidate_text, transition_count = re.subn(
        r"(?m)^Status:[ \t]*candidate[ \t]*$",
        f"Status: promoted\nPromoted-To: {new_id}",
        candidate.text,
        count=1,
    )
    if transition_count != 1:
        blockers.append("Candidate transition requires exactly one canonical Status: candidate field")
    prospective_entry_text = render_active_entry(
        active_kind,
        new_id,
        candidate.structured.title,
        candidate.structured.field_bodies.get("Statement", ""),
        None,
        candidate.scope,
        evidence,
        subject=subject_id or None,
        facet=facet or None,
        promoted_from=candidate.entry_id,
    )
    prospective_candidate = parse_structured_entries(
        memory_dir / candidate.source, promoted_candidate_text,
    )
    prospective_active = parse_structured_entries(target_path, prospective_entry_text)
    if len(prospective_candidate) != 1:
        blockers.append("Candidate transition does not produce exactly one structured Entry")
    if len(prospective_active) != 1:
        blockers.append("Promotion target does not produce exactly one structured Entry")
    if len(prospective_candidate) == 1:
        blockers.extend(structured_entry_schema_issues(prospective_candidate[0], candidate.source))
        blockers.extend(structured_entry_storage_issues(prospective_candidate[0], candidate.source))
    if len(prospective_active) == 1:
        blockers.extend(structured_entry_schema_issues(prospective_active[0], target))
        blockers.extend(structured_entry_storage_issues(prospective_active[0], target))
        if active_kind in {"decision", "constraint", "tombstone", "do-not-use", "area"}:
            blockers.extend(
                f"{issue.field}: {issue.message}"
                for issue in active_structural_operand_issues(
                    prospective_active[0], subject_index(subjects),
                )
            )
    if len(prospective_candidate) == 1 and len(prospective_active) == 1:
        blockers.extend(structured_relation_issues([prospective_candidate[0], prospective_active[0]]))
    blockers = sorted(set(blockers))
    dependency_parts = [
        f"manifest:{digest_text(manifest)}",
        f"subjects:{digest_text(read_managed_text(memory_dir, memory_dir / 'subjects.md'))}",
        f"candidate:{candidate.source}:{digest_text(candidate.text)}",
        f"target:{target}:exists={target_exists}:{digest_text(target_baseline)}",
        f"resulting-manifest:{digest_text(updated_manifest)}",
        *(
            f"local-overlay:{part}"
            for part in sorted(local_dependencies)
        ),
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
    target_files = [candidate.source, target]
    if manifest_changed:
        target_files.append("manifest.md")
    print(f"- Target files: {', '.join(target_files)}")
    if manifest_changed:
        print(f"- Manifest mutation: index {target} as an explicit-only optional module")
    if subject_id and facet:
        print(f"- Resulting structural identity: {candidate.scope}+{subject_id}+{facet}")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    print(f"Plan ID: {hashlib.sha256(plan_seed).hexdigest()[:16]}")
    print("Transactional promotion apply requires Protocol 0.8.")
    return 0
