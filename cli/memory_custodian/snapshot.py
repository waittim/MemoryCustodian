"""Shared managed-memory snapshot and inventory boundary.

The command modules used to each build a slightly different view of managed
memory.  A snapshot is the one read-only inventory used by conflict review,
ordinary checks, integrity checks, and in-memory mutation previews.  Its
``planned_text`` overlay is deliberately narrow: it can replace the text of
existing managed files without writing anything to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .entries import (
    CANDIDATE_ONLY_EVIDENCE,
    StructuredEntry,
    parse_entry_inventory,
    structured_entry_schema_issues,
    structured_relation_issues,
)
from .protocol import (
    canonical_memory_files,
    managed_markdown_files,
    read_managed_text,
)
from .reconciliations import (
    ReconciliationIssue,
    ReconciliationRecord,
    parse_reconciliations,
    validate_reconciliations,
)
from .subjects import (
    FACETS,
    Subject,
    parse_subject_registry,
    subject_registry_issues,
)


@dataclass(frozen=True)
class SnapshotFile:
    """One managed Markdown file and all parsed formal Entries it contains."""

    path: Path
    relative: str
    text: str
    entries: tuple[StructuredEntry, ...]
    entry_issues: tuple[str, ...]
    conflict_entry_issues: tuple[str, ...]
    check_issues: tuple[str, ...]
    check_warnings: tuple[str, ...]
    canonical: bool
    archive: bool


@dataclass(frozen=True)
class MemorySnapshot:
    """A complete, read-only view of shared managed memory.

    ``entries`` is the live canonical Entry universe.  ``relation_entries``
    includes archive entries because lifecycle and reconciliation operands may
    legitimately point to historical records.  File text and all parser
    diagnostics come from the same source map, including any planned overlay.
    """

    memory_dir: Path
    project_root: Path
    files: tuple[SnapshotFile, ...]
    entries: tuple[StructuredEntry, ...]
    relation_entries: tuple[StructuredEntry, ...]
    subjects: tuple[Subject, ...]
    subject_parse_issues: tuple[str, ...]
    subject_issues: tuple[str, ...]
    reconciliations: tuple[ReconciliationRecord, ...]
    reconciliation_parse_issues: tuple[str, ...]
    reconciliation_issues: tuple[ReconciliationIssue, ...]
    # ``relation_entries`` is the canonical live+archive universe used by
    # conflict analysis and the public canonical_entries() compatibility
    # helper.  Integrity also needs to reason about formal entries in a
    # managed-but-not-yet-declared optional file, so retain that complete
    # parsed universe separately rather than reparsing it in integrity.py.
    integrity_entries: tuple[StructuredEntry, ...]
    relation_issues: tuple[str, ...]
    integrity_relation_issues: tuple[str, ...]

    @property
    def canonical_paths(self) -> frozenset[Path]:
        return frozenset(item.path for item in self.files if item.canonical)

    @property
    def archive_paths(self) -> frozenset[Path]:
        return frozenset(item.path for item in self.files if item.archive)

    @property
    def entry_issues(self) -> tuple[str, ...]:
        return tuple(
            issue
            for item in self.files
            for issue in item.entry_issues
        )


def _infer_project_root(memory_dir: Path) -> Path:
    for parent in (memory_dir, *memory_dir.parents):
        if parent.name == "docs":
            return parent.parent
    return memory_dir.parent.parent


def _overlay_text(
    memory_dir: Path,
    path: Path,
    planned_text: dict[Path, str],
) -> str:
    """Read one path from the planned map when present, otherwise disk."""

    if path in planned_text:
        return planned_text[path]
    relative = path.relative_to(memory_dir)
    relative_key = memory_dir / relative
    if relative_key in planned_text:
        return planned_text[relative_key]
    return read_managed_text(memory_dir, path)


def _normalize_overlay(
    memory_dir: Path,
    planned_text: dict[Path, str] | None,
) -> dict[Path, str]:
    if not planned_text:
        return {}
    normalized: dict[Path, str] = {}
    for path, text in planned_text.items():
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = memory_dir / candidate
        normalized[candidate] = text
    return normalized


def _entry_semantic_diagnostics(
    files: tuple[SnapshotFile, ...],
    subjects: tuple[Subject, ...],
) -> tuple[dict[Path, tuple[str, ...]], dict[Path, tuple[str, ...]]]:
    """Return check-only semantic diagnostics for already parsed Entries.

    Structural syntax and storage checks live in ``parse_entry_inventory``.
    These are the remaining project-level admission rules historically kept
    in ``check.py``: active evidence policy, Subject/Facet identity, and
    candidate provisional identity.  Keeping them here means every command
    that needs a complete snapshot observes the same rules without parsing a
    second time.
    """

    active_subjects: dict[str, Subject] = {}
    for subject in subjects:
        if subject.status == "active":
            active_subjects[subject.subject_id.casefold()] = subject

    issues_by_path: dict[Path, list[str]] = {item.path: [] for item in files}
    warnings_by_path: dict[Path, list[str]] = {item.path: [] for item in files}
    for item in files:
        if item.archive:
            continue
        relative = item.relative
        for entry in item.entries:
            if entry.status == "active":
                if not entry.evidence:
                    issues_by_path[item.path].append(
                        f"{relative}: active entry {entry.entry_id} has no Evidence"
                    )
                elif all(value in CANDIDATE_ONLY_EVIDENCE for value in entry.evidence):
                    issues_by_path[item.path].append(
                        f"{relative}: active entry {entry.entry_id} has only unconfirmed Evidence"
                    )
                if "legacy-unverified" in entry.evidence:
                    warnings_by_path[item.path].append(
                        f"{relative}: {entry.entry_id} uses migration-only legacy-unverified Evidence"
                    )

            if entry.status == "active":
                code = entry.entry_id.split("-", 2)[1].upper()
                if code in {"DEC", "CON", "DNU", "AREA"}:
                    subject_id = entry.fields.get("Subject", "")
                    facet = entry.fields.get("Facet", "")
                    if not subject_id or not facet:
                        warnings_by_path[item.path].append(
                            f"{relative}: {entry.entry_id} legacy Subject/Facet coverage is incomplete"
                        )
                    else:
                        if subject_id.casefold() not in active_subjects:
                            issues_by_path[item.path].append(
                                f"{relative}: {entry.entry_id} references missing or inactive Subject {subject_id}"
                            )
                        if facet not in FACETS:
                            issues_by_path[item.path].append(
                                f"{relative}: {entry.entry_id} has invalid Facet {facet!r}"
                            )

            if entry.status in {"candidate", "promoted"}:
                provisional_subject = entry.fields.get("Provisional-Subject", "")
                provisional_facet = entry.fields.get("Provisional-Facet", "")
                # Pairing is a schema rule and is already emitted by the
                # shared schema validator.  Only validate the references when
                # both operands are present.
                if provisional_subject and provisional_facet:
                    if provisional_subject.casefold() not in active_subjects:
                        issues_by_path[item.path].append(
                            f"{relative}: {entry.entry_id} references missing or inactive "
                            f"Provisional-Subject {provisional_subject}"
                        )
                    if provisional_facet not in FACETS:
                        issues_by_path[item.path].append(
                            f"{relative}: {entry.entry_id} has invalid "
                            f"Provisional-Facet {provisional_facet!r}"
                        )

    return (
        {path: tuple(dict.fromkeys(values)) for path, values in issues_by_path.items()},
        {path: tuple(dict.fromkeys(values)) for path, values in warnings_by_path.items()},
    )


def _conflict_entry_issues(
    relative: str,
    entries: tuple[StructuredEntry, ...],
    issues: tuple[str, ...],
) -> tuple[str, ...]:
    """Select entry diagnostics that make a conflict decision unsafe.

    ``do-not-use.md`` intentionally remains a mixed-format migration surface:
    a newly prepended formal Tombstone may be followed by an older top-level
    legacy bullet.  The Markdown parser reports that boundary as ambiguous so
    ordinary ``check`` can recommend a rewrite, but it is not an Entry schema
    or relation failure and must not make a safe forget plan impossible.  The
    unit-level blocker still protects a forget that targets that bullet.
    """

    if relative != "do-not-use.md" or not any(
        entry.entry_id.split("-", 2)[1].upper() in {"DNU", "TOMB"}
        for entry in entries
    ):
        return issues
    return tuple(
        issue
        for issue in issues
        if getattr(issue, "conflict_relevant", True)
    )


def build_snapshot(
    memory_dir: Path,
    project_root: Path | None = None,
    *,
    planned_text: dict[Path, str] | None = None,
) -> MemorySnapshot:
    """Build one complete managed-memory inventory from disk or an overlay."""

    memory_dir = Path(memory_dir)
    project_root = (
        Path(project_root)
        if project_root is not None
        else _infer_project_root(memory_dir)
    )
    overlay = _normalize_overlay(memory_dir, planned_text)

    inventory = managed_markdown_files(memory_dir)
    canonical = canonical_memory_files(memory_dir, include_archive=True)
    canonical_keys = {
        path.relative_to(memory_dir).as_posix()
        for path in canonical
    }
    files: list[SnapshotFile] = []
    for path in inventory:
        relative = path.relative_to(memory_dir).as_posix()
        text = _overlay_text(memory_dir, path, overlay)
        archive = relative.startswith("archive/")
        if relative in {"subjects.md", "reconciliations.md"}:
            entries: tuple[StructuredEntry, ...] = ()
            entry_issues: tuple[str, ...] = ()
            conflict_entry_issues: tuple[str, ...] = ()
        else:
            parsed, parsed_issues = parse_entry_inventory(
                path,
                text,
                relative,
                project_root,
                require_active_identity=False,
            )
            entries = tuple(parsed)
            entry_issues = tuple(parsed_issues)
            required_identity = (
                []
                if not (relative in canonical_keys)
                else [
                    issue
                    for entry in entries
                    for issue in structured_entry_schema_issues(
                        entry,
                        relative,
                        require_active_identity=not archive,
                    )
                ]
            )
            conflict_entry_issues = _conflict_entry_issues(
                relative,
                entries,
                tuple(dict.fromkeys([*entry_issues, *required_identity])),
            )
        files.append(
            SnapshotFile(
                path,
                relative,
                text,
                entries,
                entry_issues,
                conflict_entry_issues,
                entry_issues,
                (),
                relative in canonical_keys,
                archive,
            )
        )

    subject_path = memory_dir / "subjects.md"
    if subject_path.exists() or subject_path in overlay:
        subject_text = _overlay_text(memory_dir, subject_path, overlay)
        try:
            subjects, subject_parse_issues = parse_subject_registry(
                subject_path,
                subject_text,
            )
        except (TypeError, ValueError) as exc:
            subjects = []
            subject_parse_issues = [
                f"subjects.md: Subject registry parsing failed: {exc}"
            ]
    else:
        subjects = []
        subject_parse_issues = ["subjects.md: missing managed Subject registry"]
    subject_issues = subject_registry_issues(
        subjects,
        subject_parse_issues,
        project_root,
    )

    live_entries = tuple(
        entry
        for item in files
        if item.canonical and not item.archive
        for entry in item.entries
    )
    relation_entries = tuple(
        entry
        for item in files
        if item.canonical
        for entry in item.entries
    )
    integrity_entries = tuple(
        entry
        for item in files
        if item.relative not in {"subjects.md", "reconciliations.md"}
        and item.path.name.casefold() != "readme.md"
        for entry in item.entries
    )
    merged_subject_ids = {
        subject.subject_id
        for subject in subjects
        if subject.status == "merged"
    }
    relation_issues = tuple(
        structured_relation_issues(
            list(relation_entries),
            merged_subject_ids=merged_subject_ids,
        )
    )
    integrity_relation_issues = tuple(
        structured_relation_issues(
            list(integrity_entries),
            merged_subject_ids=merged_subject_ids,
        )
    )

    reconciliation_path = memory_dir / "reconciliations.md"
    if reconciliation_path.exists() or reconciliation_path in overlay:
        reconciliation_text = _overlay_text(memory_dir, reconciliation_path, overlay)
        try:
            records, reconciliation_parse_issues = parse_reconciliations(
                reconciliation_path,
                reconciliation_text,
                project_root,
                include_invalid=True,
            )
        except (TypeError, ValueError) as exc:
            records = ()
            reconciliation_parse_issues = (
                f"reconciliations.md: Reconciliation parsing failed: {exc}",
            )
    else:
        records = ()
        reconciliation_parse_issues = ()
    _valid_records, reconciliation_issues = validate_reconciliations(
        tuple(records),
        tuple(reconciliation_parse_issues),
        relation_entries,
        tuple(subjects),
    )

    provisional_files = tuple(files)
    semantic_issues, semantic_warnings = _entry_semantic_diagnostics(
        provisional_files,
        tuple(subjects),
    )
    finalized_files = tuple(
        SnapshotFile(
            item.path,
            item.relative,
            item.text,
            item.entries,
            item.entry_issues,
            item.conflict_entry_issues,
            tuple(dict.fromkeys([*item.check_issues, *semantic_issues[item.path]])),
            semantic_warnings[item.path],
            item.canonical,
            item.archive,
        )
        for item in provisional_files
    )
    return MemorySnapshot(
        memory_dir,
        project_root,
        finalized_files,
        live_entries,
        relation_entries,
        tuple(subjects),
        tuple(subject_parse_issues),
        tuple(subject_issues),
        tuple(records),
        tuple(reconciliation_parse_issues),
        tuple(reconciliation_issues),
        integrity_entries,
        relation_issues,
        integrity_relation_issues,
    )
