"""Deterministic Protocol 0.7 structural conflict analysis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .entries import (
    StructuredEntry,
    parse_entry_inventory,
    parse_structured_entries,
    structured_relation_issues,
)
from .reconciliations import parse_reconciliations, validate_reconciliations
from .structural import active_structural_operand_issues, subject_index
from .subjects import (
    Subject, load_subjects, normalize_alias, normalize_canonical_ref,
    validate_subject_registry,
)
from .protocol import canonical_memory_files, managed_markdown_files, read_managed_text


class ConflictStatus(str, Enum):
    CLEAR = "CLEAR"
    REVIEW = "REVIEW"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"


@dataclass(frozen=True)
class ConflictFinding:
    code: str
    status: ConflictStatus
    message: str
    entry_ids: tuple[str, ...] = ()
    subject_id: str = ""
    facet: str = ""
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConflictResult:
    status: ConflictStatus
    findings: tuple[ConflictFinding, ...]


def _status(findings: list[ConflictFinding]) -> ConflictStatus:
    for candidate in (ConflictStatus.INVALID, ConflictStatus.CONFLICT, ConflictStatus.REVIEW):
        if any(item.status == candidate for item in findings):
            return candidate
    return ConflictStatus.CLEAR


def canonical_entries(memory_dir: Path, *, include_archive: bool = False) -> tuple[StructuredEntry, ...]:
    entries: list[StructuredEntry] = []
    if not memory_dir.exists():
        return ()
    for path in canonical_memory_files(memory_dir, include_archive=include_archive):
        relative = path.relative_to(memory_dir).as_posix()
        try:
            entries.extend(parse_structured_entries(path, read_managed_text(memory_dir, path)))
        except ValueError:
            # The integrity pass in analyze_conflicts emits the actionable
            # finding; index consumers should still be able to inventory the
            # remaining valid units.
            continue
    return tuple(entries)


def _subject_findings(subject_records: Sequence[Subject]) -> list[ConflictFinding]:
    findings: list[ConflictFinding] = []
    refs: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for subject in subject_records:
        key = subject.subject_id.casefold()
        for alias in (subject.title, *subject.aliases):
            normalized = normalize_alias(alias)
            owner = aliases.get(normalized)
            if subject.status == "active" and owner and owner != key:
                findings.append(ConflictFinding(
                    "MC-CONFLICT-004", ConflictStatus.CONFLICT,
                    f"Alias {alias!r} is owned by multiple active Subjects.",
                    subject_id=subject.subject_id,
                ))
            elif subject.status == "active":
                aliases[normalized] = key
        if subject.canonical_ref and subject.status == "active":
            try:
                normalized_ref = normalize_canonical_ref(subject.canonical_ref)
            except ValueError as exc:
                findings.append(ConflictFinding(
                    "MC-CONFLICT-003", ConflictStatus.INVALID, str(exc),
                    subject_id=subject.subject_id,
                ))
                continue
            owner = refs.get(normalized_ref)
            if owner and owner != key:
                findings.append(ConflictFinding(
                    "MC-CONFLICT-003", ConflictStatus.CONFLICT,
                    f"Canonical-Ref {normalized_ref!r} is owned by multiple active Subjects.",
                    subject_id=subject.subject_id,
                ))
            refs[normalized_ref] = key
    return findings


def _entry_index(entries: tuple[StructuredEntry, ...]) -> dict[str, list[StructuredEntry]]:
    result: dict[str, list[StructuredEntry]] = {}
    for entry in entries:
        result.setdefault(entry.entry_id.casefold(), []).append(entry)
    return result


def analyze_conflicts(
    memory_dir: Path,
    *,
    matched_areas: tuple[str, ...] = (),
    included_modules: tuple[str, ...] | None = None,
) -> ConflictResult:
    project_root = next(
        (parent.parent for parent in (memory_dir, *memory_dir.parents) if parent.name == "docs"),
        memory_dir.parent.parent,
    )
    subject_records = load_subjects(memory_dir)
    findings = [
        ConflictFinding("MC-CONFLICT-003", ConflictStatus.INVALID, issue)
        for issue in validate_subject_registry(memory_dir, project_root)
    ]
    findings.extend(_subject_findings(subject_records))
    structural_subjects = subject_index(subject_records)
    # Keep live entries as the owner/context universe.  Lifecycle relations
    # and Entry-ID uniqueness, however, span the managed archive as well: a
    # current Entry may legitimately supersede a historical Entry that has
    # already been moved out of the live canonical file.
    entries = canonical_entries(memory_dir)
    relation_entries = canonical_entries(memory_dir, include_archive=True)
    canonical_paths = set(canonical_memory_files(memory_dir))
    integrity_paths = set(canonical_memory_files(memory_dir, include_archive=True))
    for path in integrity_paths:
        relative = path.relative_to(memory_dir).as_posix()
        parsed, entry_issues = parse_entry_inventory(
            path, read_managed_text(memory_dir, path), relative, project_root,
            require_active_identity=not relative.startswith("archive/"),
        )
        findings.extend(
            ConflictFinding(
                "MC-CONFLICT-007", ConflictStatus.INVALID, issue,
                tuple(entry.entry_id for entry in parsed if entry.entry_id),
            )
            for issue in entry_issues
        )
    for path in managed_markdown_files(memory_dir):
        if path in canonical_paths or path.name.casefold() == "readme.md":
            continue
        if path.relative_to(memory_dir).as_posix().startswith("archive/"):
            continue
        for entry in parse_structured_entries(path, read_managed_text(memory_dir, path)):
            if entry.status == "active":
                findings.append(ConflictFinding(
                    "MC-CONFLICT-007", ConflictStatus.INVALID,
                    "Active Entry is outside canonical manifest-authorized storage.",
                    (entry.entry_id,),
                ))
    selected_modules = set(included_modules) if included_modules is not None else None
    by_id = _entry_index(entries)
    relation_by_id = _entry_index(relation_entries)
    for matches in relation_by_id.values():
        if len(matches) > 1:
            findings.append(ConflictFinding(
                "MC-CONFLICT-008", ConflictStatus.INVALID,
                "Duplicate Entry ID prevents deterministic relation resolution.",
                tuple(entry.entry_id for entry in matches),
            ))
    merged_subject_ids = {
        subject.subject_id
        for subject in subject_records
        if subject.status == "merged"
    }
    for issue in structured_relation_issues(
        list(relation_entries), merged_subject_ids=merged_subject_ids,
    ):
        entry_ids = tuple(
            entry.entry_id
            for entry in relation_entries
            if entry.entry_id.casefold() in issue.casefold()
        )
        findings.append(ConflictFinding(
            "MC-CONFLICT-008", ConflictStatus.INVALID,
            f"Invalid Entry relation: {issue}", entry_ids,
        ))
    owners: dict[tuple[str, str, str], list[StructuredEntry]] = {}
    by_subject_facet: dict[tuple[str, str], list[StructuredEntry]] = {}

    for entry in entries:
        if entry.status == "active" and entry.fields.get("Subject"):
            operand_issues = active_structural_operand_issues(entry, structural_subjects)
            if operand_issues:
                for issue in operand_issues:
                    if issue.field == "Status":
                        continue
                    code = "MC-CONFLICT-005" if issue.field == "Subject" else "MC-CONFLICT-007"
                    findings.append(ConflictFinding(
                        code, ConflictStatus.INVALID, issue.message,
                        (entry.entry_id,), entry.fields.get("Subject", ""),
                        entry.fields.get("Facet", ""), (entry.scope,),
                    ))
        if entry.status != "active":
            continue
        code = entry.entry_id.split("-", 2)[1].upper()
        # MC-TOMB is a content-minimized erasure guard, not a structural
        # invariant owner. Requiring it to retain a Subject would defeat hard
        # forgetting; ordinary DNU entries remain governed owners.
        if code not in {"DEC", "CON", "DNU", "AREA"}:
            continue
        relative = entry.path.relative_to(memory_dir).as_posix()
        if selected_modules is not None and relative not in selected_modules:
            continue
        if relative.startswith(("rules/", "profiles/")):
            continue
        subject_id = entry.fields.get("Subject", "")
        facet = entry.fields.get("Facet", "")
        operand_issues = active_structural_operand_issues(entry, structural_subjects)
        for issue in operand_issues:
            code = "MC-CONFLICT-005" if issue.field == "Subject" else "MC-CONFLICT-007"
            findings.append(ConflictFinding(
                code, ConflictStatus.INVALID,
                issue.message,
                (entry.entry_id,), subject_id, facet, (entry.scope,),
            ))
        if operand_issues:
            continue
        identity = (entry.scope.casefold(), subject_id.casefold(), facet.casefold())
        owners.setdefault(identity, []).append(entry)
        by_subject_facet.setdefault((subject_id.casefold(), facet.casefold()), []).append(entry)
        if entry.fields.get("Exception-To") and not entry.scope.startswith("area:"):
            findings.append(ConflictFinding(
                "MC-CONFLICT-006", ConflictStatus.INVALID,
                "Exception-To is valid only on an active area-scoped entry.",
                (entry.entry_id, entry.fields["Exception-To"]), subject_id, facet,
                (entry.scope,),
            ))

    for entry in entries:
        if entry.status != "active" or not entry.fields.get("Exception-To"):
            continue
        target_matches = by_id.get(entry.fields["Exception-To"].casefold(), [])
        valid = (
            entry.scope.startswith("area:")
            and len(target_matches) == 1
            and target_matches[0].status == "active"
            and target_matches[0].scope == "project"
            and not target_matches[0].fields.get("Exception-To")
            and entry.fields.get("Subject", "").casefold()
            == target_matches[0].fields.get("Subject", "").casefold()
            and entry.fields.get("Facet", "").casefold()
            == target_matches[0].fields.get("Facet", "").casefold()
        )
        if not valid:
            findings.append(ConflictFinding(
                "MC-CONFLICT-006", ConflictStatus.INVALID,
                "Invalid Exception-To relation.",
                (entry.entry_id, entry.fields["Exception-To"]),
                entry.fields.get("Subject", ""), entry.fields.get("Facet", ""),
                (entry.scope, "project"),
            ))

    for (scope, subject_id, facet), matches in sorted(owners.items()):
        if len(matches) > 1:
            findings.append(ConflictFinding(
                "MC-CONFLICT-001", ConflictStatus.CONFLICT,
                "Multiple active owners for one structural identity.",
                tuple(sorted(entry.entry_id for entry in matches)), subject_id, facet, (scope,),
            ))

    for (subject_id, facet), matches in sorted(by_subject_facet.items()):
        project_entries = [entry for entry in matches if entry.scope == "project"]
        area_entries = [entry for entry in matches if entry.scope.startswith("area:")]
        for area_entry in area_entries:
            exception_to = area_entry.fields.get("Exception-To", "")
            if exception_to:
                targets = by_id.get(exception_to.casefold(), [])
                valid = (
                    len(targets) == 1
                    and targets[0].status == "active"
                    and targets[0].scope == "project"
                    and targets[0].fields.get("Subject", "").casefold() == subject_id
                    and targets[0].fields.get("Facet", "").casefold() == facet
                )
                if not valid:
                    findings.append(ConflictFinding(
                        "MC-CONFLICT-006", ConflictStatus.INVALID,
                        "Invalid Exception-To relation.",
                        (area_entry.entry_id, exception_to), subject_id, facet,
                        (area_entry.scope, "project"),
                    ))
            elif project_entries:
                findings.append(ConflictFinding(
                    "MC-CONFLICT-002", ConflictStatus.REVIEW,
                    "Project/area overlap requires explicit exception review.",
                    tuple(sorted([area_entry.entry_id, *(entry.entry_id for entry in project_entries)])),
                    subject_id, facet, ("project", area_entry.scope),
                ))

        matched = [
            entry for entry in area_entries
            if entry.scope.removeprefix("area:") in set(matched_areas)
        ]
        matched_scopes = {entry.scope for entry in matched}
        if len(matched_scopes) > 1:
            findings.append(ConflictFinding(
                "MC-CONFLICT-009", ConflictStatus.REVIEW,
                "Matched areas expose overlapping Subject/Facet ownership.",
                tuple(sorted(entry.entry_id for entry in matched)), subject_id, facet,
                tuple(sorted(matched_scopes)),
            ))

    # Reconciliation records may acknowledge a live Entry against its
    # historical replacement in archive/.  Validate those records against
    # the same full lifecycle inventory used above, while keeping `entries`
    # (and therefore owner/conflict analysis) live-only.
    findings.extend(_reconciliation_findings(memory_dir, relation_by_id))
    unique = {
        (item.code, item.status, item.message, item.entry_ids, item.subject_id, item.facet, item.scopes): item
        for item in findings
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (item.code, item.subject_id, item.facet, item.scopes, item.entry_ids),
    )
    return ConflictResult(_status(ordered), tuple(ordered))


def _reconciliation_findings(
    memory_dir: Path,
    entries: dict[str, list[StructuredEntry]],
) -> list[ConflictFinding]:
    path = memory_dir / "reconciliations.md"
    if not path.exists():
        return []
    project_root = next(
        (parent.parent for parent in (memory_dir, *memory_dir.parents) if parent.name == "docs"),
        memory_dir.parent.parent,
    )
    records, parse_issues = parse_reconciliations(
        path, read_managed_text(memory_dir, path), project_root, include_invalid=True
    )
    all_entries = tuple(entry for matches in entries.values() for entry in matches)
    _valid, issues = validate_reconciliations(
        records, parse_issues, all_entries, load_subjects(memory_dir),
    )
    return [
        ConflictFinding(
            "MC-CONFLICT-008", ConflictStatus.INVALID,
            f"Invalid or inconsistent reconciliation record: {issue.message}",
            issue.entries,
        )
        for issue in issues
    ]


def render_conflict_result(result: ConflictResult) -> None:
    print(f"Conflict status: {result.status.value}")
    for finding in result.findings:
        identity = ""
        if finding.subject_id or finding.facet or finding.scopes:
            identity = (
                f" [Subject: {finding.subject_id or '-'}; Facet: {finding.facet or '-'}; "
                f"Scope: {', '.join(finding.scopes) or '-'}]"
            )
        entries = f" Entries: {', '.join(finding.entry_ids)}." if finding.entry_ids else ""
        print(f"- {finding.code} {finding.status.value}: {finding.message}{identity}{entries}")
