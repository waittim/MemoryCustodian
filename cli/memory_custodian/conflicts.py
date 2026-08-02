"""Deterministic Protocol 0.7 structural conflict analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from .entries import StructuredEntry, parse_structured_entries
from .subjects import FACETS, load_subjects, normalize_alias, normalize_canonical_ref


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
    for path in sorted(memory_dir.rglob("*.md")):
        relative = path.relative_to(memory_dir).as_posix()
        if relative == "subjects.md" or (relative.startswith("archive/") and not include_archive):
            continue
        entries.extend(parse_structured_entries(path, path.read_text(encoding="utf-8")))
    return tuple(entries)


def _subject_findings(memory_dir: Path) -> tuple[list[ConflictFinding], dict[str, object]]:
    findings: list[ConflictFinding] = []
    active: dict[str, object] = {}
    refs: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for subject in load_subjects(memory_dir):
        key = subject.subject_id.casefold()
        if subject.status == "active":
            active[key] = subject
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
    return findings, active


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
    findings, subjects = _subject_findings(memory_dir)
    entries = canonical_entries(memory_dir)
    selected_modules = set(included_modules) if included_modules is not None else None
    by_id = _entry_index(entries)
    for matches in by_id.values():
        if len(matches) > 1:
            findings.append(ConflictFinding(
                "MC-CONFLICT-008", ConflictStatus.INVALID,
                "Duplicate Entry ID prevents deterministic relation resolution.",
                tuple(entry.entry_id for entry in matches),
            ))
    owners: dict[tuple[str, str, str], list[StructuredEntry]] = {}
    by_subject_facet: dict[tuple[str, str], list[StructuredEntry]] = {}

    for entry in entries:
        if entry.status != "active":
            continue
        code = entry.entry_id.split("-", 2)[1].upper()
        if code not in {"DEC", "CON", "DNU", "AREA", "TOMB"}:
            continue
        relative = entry.path.relative_to(memory_dir).as_posix()
        if selected_modules is not None and relative not in selected_modules:
            continue
        if relative.startswith(("rules/", "profiles/")):
            continue
        subject_id = entry.fields.get("Subject", "")
        facet = entry.fields.get("Facet", "")
        if not subject_id or not facet:
            findings.append(ConflictFinding(
                "MC-CONFLICT-007", ConflictStatus.INVALID,
                "Managed hard-memory entry lacks Subject or Facet.",
                (entry.entry_id,), subject_id, facet, (entry.scope,),
            ))
            continue
        subject = subjects.get(subject_id.casefold())
        if subject is None:
            findings.append(ConflictFinding(
                "MC-CONFLICT-005", ConflictStatus.INVALID,
                "Subject reference is missing, inactive, or merged.",
                (entry.entry_id,), subject_id, facet, (entry.scope,),
            ))
        if facet not in FACETS:
            findings.append(ConflictFinding(
                "MC-CONFLICT-007", ConflictStatus.INVALID,
                f"Managed hard-memory entry has invalid Facet {facet!r}.",
                (entry.entry_id,), subject_id, facet, (entry.scope,),
            ))
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

    findings.extend(_reconciliation_findings(memory_dir, by_id, subjects))
    unique = {
        (item.code, item.status, item.message, item.entry_ids, item.subject_id, item.facet, item.scopes): item
        for item in findings
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (item.code, item.subject_id, item.facet, item.scopes, item.entry_ids),
    )
    return ConflictResult(_status(ordered), tuple(ordered))


_REC_ID_RE = re.compile(r"^## (MC-REC-\d{8}-[0-9a-f]{8})\s+—\s+(.+)$", re.I)


def _reconciliation_findings(
    memory_dir: Path,
    entries: dict[str, list[StructuredEntry]],
    _active_subjects: dict[str, object],
) -> list[ConflictFinding]:
    path = memory_dir / "reconciliations.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)(?=^## MC-REC-)", text)
    findings: list[ConflictFinding] = []
    identities: set[tuple[str, ...]] = set()
    registry_subjects = {item.subject_id.casefold(): item for item in load_subjects(memory_dir)}
    for section in sections:
        lines = section.strip().splitlines()
        if not lines or not _REC_ID_RE.fullmatch(lines[0]):
            continue
        status = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Status:")), "")
        resolution = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Resolution:")), "")
        entry_ids = tuple(sorted({line[2:].strip() for line in lines if line.startswith("- MC-")}))
        evidence = tuple(line[2:].strip() for line in lines if line.startswith("- ") and not line.startswith("- MC-"))
        resolved_entries = [entries[value.casefold()][0] for value in entry_ids if len(entries.get(value.casefold(), [])) == 1]
        evidence_valid = bool(evidence) and all(
            item == "user-confirmed"
            or item == "legacy-unverified"
            or item.split(":", 1)[0] in {"repo", "doc", "test", "issue", "pr", "migration"}
            for item in evidence
        )
        relation_valid = True
        if resolution == "superseded":
            relation_valid = any(
                left.fields.get("Superseded-By", "").casefold() == right.entry_id.casefold()
                and right.fields.get("Supersedes", "").casefold() == left.entry_id.casefold()
                for left in resolved_entries for right in resolved_entries if left is not right
            )
        elif resolution == "exception":
            relation_valid = any(
                left.fields.get("Exception-To", "").casefold() == right.entry_id.casefold()
                and left.scope.startswith("area:") and right.scope == "project"
                and left.fields.get("Subject", "").casefold() == right.fields.get("Subject", "").casefold()
                and left.fields.get("Facet", "").casefold() == right.fields.get("Facet", "").casefold()
                for left in resolved_entries for right in resolved_entries if left is not right
            )
        elif resolution == "subject-merged":
            relation_valid = any(
                getattr(registry_subjects.get(left.fields.get("Subject", "").casefold()), "status", "") == "merged"
                and getattr(registry_subjects.get(left.fields.get("Subject", "").casefold()), "merged_into", "").casefold()
                == right.fields.get("Subject", "").casefold()
                for left in resolved_entries for right in resolved_entries if left is not right
            )
        valid = (
            status == "active"
            and resolution in {"distinct", "superseded", "exception", "subject-merged"}
            and len(entry_ids) >= 2
            and evidence_valid
            and all(len(entries.get(value.casefold(), [])) == 1 for value in entry_ids)
            and entry_ids not in identities
            and relation_valid
        )
        if not valid:
            findings.append(ConflictFinding(
                "MC-CONFLICT-008", ConflictStatus.INVALID,
                "Invalid or inconsistent reconciliation record.", entry_ids,
            ))
        identities.add(entry_ids)
    return findings


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
