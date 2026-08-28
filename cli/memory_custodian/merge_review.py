"""Best-effort, read-only Git merge reconciliation review."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess

from .entries import (
    StructuredEntry,
    parse_entry_inventory,
    structured_relation_issues,
)
from .reconciliations import (
    ReconciliationIssue,
    ReconciliationRecord,
    parse_reconciliations,
    reconciliation_pairs,
    validate_reconciliations,
)
from .subjects import (
    Subject, normalize_alias, normalize_canonical_ref, parse_subject_registry,
    subject_registry_issues,
)
from .protocol import CURRENT_ENTRY_SCHEMA_VERSION, entry_schema_version_for_manifest
from .structural import active_structural_operand_issues, subject_index


@dataclass(frozen=True)
class MergeReviewResult:
    text: str
    blocking: bool


@dataclass(frozen=True)
class _DeletedEntry:
    entry_id: str
    path: Path
    text: str = ""
    status: str = "deleted"
    scope: str = ""
    fields: dict[str, str] = field(default_factory=dict)


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=project_root, text=True, capture_output=True,
        check=False, timeout=20,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "Git command failed")
    return result.stdout


def _show(project_root: Path, revision: str, path: str) -> str:
    try:
        return _git(project_root, "show", f"{revision}:{path}")
    except ValueError as exc:
        # A valid revision may legitimately omit an optional managed file (or
        # predate the Subject registry).  Keep that historical behavior, but
        # do not turn an unrelated Git failure into an empty file: the caller
        # must report that review as unavailable and block it.  A second,
        # exact ls-tree lookup distinguishes the two cases without relying on
        # localized `git show` diagnostics.
        try:
            listed = _git(project_root, "ls-tree", "-r", "--name-only", revision, "--", path)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise exc
        if path not in listed.splitlines():
            return ""
        raise


def _files(project_root: Path, revision: str, memory_relative: str) -> tuple[str, ...]:
    output = _git(project_root, "ls-tree", "-r", "--name-only", revision, "--", memory_relative)
    return tuple(sorted(
        line for line in output.splitlines()
        if line.endswith(".md")
        and Path(line).name.casefold() != "readme.md"
        and line.startswith(memory_relative.rstrip("/") + "/")
    ))


def _entries(
    project_root: Path,
    revision: str,
    files: tuple[str, ...],
    memory_relative: str,
    *,
    subjects: tuple[Subject, ...] = (),
    merged_subject_ids: set[str] | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> tuple[tuple[StructuredEntry, ...], tuple[str, ...]]:
    result: list[StructuredEntry] = []
    issues: list[str] = []
    for relative in files:
        text = _show(project_root, revision, relative)
        prefix = memory_relative.rstrip("/") + "/"
        memory_path = relative.removeprefix(prefix)
        if memory_path in {"subjects.md", "reconciliations.md"}:
            continue
        parsed, file_issues = parse_entry_inventory(
            Path(relative), text, memory_path, project_root,
            require_active_identity=not memory_path.startswith("archive/"),
            entry_schema_version=entry_schema_version,
        )
        result.extend(parsed)
        issues.extend(file_issues)
    subject_map = subject_index(subjects)
    prefix = memory_relative.rstrip("/") + "/"
    for entry in result:
        relative = entry.path.as_posix().removeprefix(prefix)
        code = entry.entry_id.split("-", 2)[1].upper()
        if (
            entry.status == "active"
            and code in {"DEC", "CON", "DNU", "AREA"}
            and not relative.startswith("archive/")
            and not relative.startswith(("rules/", "profiles/"))
        ):
            for issue in active_structural_operand_issues(entry, subject_map):
                if issue.field in {"Subject", "Facet"}:
                    issues.append(f"{relative}: {entry.entry_id} {issue.message}")
    issues.extend(
        f"{memory_relative}: {issue}"
        for issue in structured_relation_issues(
            result, merged_subject_ids=merged_subject_ids,
        )
    )
    return tuple(result), tuple(dict.fromkeys(issues))


def _subjects(
    project_root: Path, revision: str, registry: str,
) -> tuple[tuple[Subject, ...], tuple[str, ...]]:
    text = _show(project_root, revision, registry)
    if not text:
        return (), (f"{registry}: missing managed Subject registry",)
    try:
        subjects, parse_issues = parse_subject_registry(Path(registry), text)
    except (TypeError, ValueError) as exc:
        return (), (f"{registry}: Subject registry parsing failed: {exc}",)
    return tuple(subjects), tuple(subject_registry_issues(
        subjects, parse_issues, project_root,
    ))


def _reconciliations(
    project_root: Path,
    revision: str,
    relative: str,
    entries: tuple[StructuredEntry, ...],
    subjects: tuple[Subject, ...],
) -> tuple[tuple[ReconciliationRecord, ...], tuple[ReconciliationIssue, ...]]:
    try:
        records, parse_issues = parse_reconciliations(
            Path(relative), _show(project_root, revision, relative), project_root,
            include_invalid=True,
        )
    except (TypeError, ValueError) as exc:
        parse_issues = (f"{relative}: Reconciliation parsing failed: {exc}",)
        records = ()
    valid, issues = validate_reconciliations(records, parse_issues, entries, subjects)
    return (() if issues else valid), issues


def _by_id(
    values: tuple[StructuredEntry | Subject | ReconciliationRecord, ...],
    *,
    duplicate_ids: list[str] | None = None,
) -> dict[str, StructuredEntry | Subject | ReconciliationRecord]:
    result: dict[str, StructuredEntry | Subject | ReconciliationRecord] = {}
    for value in values:
        if isinstance(value, StructuredEntry):
            identity = value.entry_id
        elif isinstance(value, Subject):
            identity = value.subject_id
        else:
            identity = value.record_id
        key = identity.casefold()
        if key in result:
            if duplicate_ids is None:
                raise ValueError(f"Duplicate canonical ID {identity}; lookup is unsafe.")
            duplicate_ids.append(identity)
            continue
        result[key] = value
    return result


def _changed(
    base: dict[str, object], side: dict[str, object], *, include_deleted: bool = False,
) -> dict[str, object]:
    if include_deleted:
        return {
            key: _DeletedEntry(value.entry_id, value.path)
            for key, value in base.items()
            if key not in side and isinstance(value, StructuredEntry)
        }
    changed = {
        key: value for key, value in side.items()
        if key not in base or getattr(base[key], "text") != getattr(value, "text")
    }
    return changed


def _changed_files(project_root: Path, base: str, revision: str) -> set[str]:
    return set(_git(project_root, "diff", "--name-only", base, revision).splitlines())


def merge_review(project_root: Path, memory_dir: Path, target_ref: str) -> MergeReviewResult:
    try:
        base = _git(project_root, "merge-base", "HEAD", target_ref).strip()
        if not base:
            raise ValueError("No merge base found")
        memory_relative = memory_dir.relative_to(project_root).as_posix()
        all_files = tuple(sorted(set(
            _files(project_root, base, memory_relative)
            + _files(project_root, "HEAD", memory_relative)
            + _files(project_root, target_ref, memory_relative)
        )))
        registry = f"{memory_relative}/subjects.md"
        reconciliations = f"{memory_relative}/reconciliations.md"
        entry_schemas = {
            revision: entry_schema_version_for_manifest(
                _show(project_root, revision, f"{memory_relative}/manifest.md")
            )
            for revision in (base, "HEAD", target_ref)
        }
        base_subject_units, _base_subject_issues = _subjects(project_root, base, registry)
        head_subject_units, head_subject_issues = _subjects(project_root, "HEAD", registry)
        target_subject_units, target_subject_issues = _subjects(project_root, target_ref, registry)
        base_entry_units, base_entry_issues = _entries(
            project_root, base, all_files, memory_relative,
            subjects=base_subject_units,
            merged_subject_ids={
                subject.subject_id
                for subject in base_subject_units
                if subject.status == "merged"
            },
            entry_schema_version=entry_schemas[base],
        )
        head_entry_units, head_entry_issues = _entries(
            project_root, "HEAD", all_files, memory_relative,
            subjects=head_subject_units,
            merged_subject_ids={
                subject.subject_id
                for subject in head_subject_units
                if subject.status == "merged"
            },
            entry_schema_version=entry_schemas["HEAD"],
        )
        target_entry_units, target_entry_issues = _entries(
            project_root, target_ref, all_files, memory_relative,
            subjects=target_subject_units,
            merged_subject_ids={
                subject.subject_id
                for subject in target_subject_units
                if subject.status == "merged"
            },
            entry_schema_version=entry_schemas[target_ref],
        )
        base_records, _base_record_issues = _reconciliations(
            project_root, base, reconciliations, base_entry_units, base_subject_units,
        )
        head_records, head_record_issues = _reconciliations(
            project_root, "HEAD", reconciliations, head_entry_units, head_subject_units,
        )
        target_records, target_record_issues = _reconciliations(
            project_root, target_ref, reconciliations, target_entry_units, target_subject_units,
        )
        duplicate_entry_ids: list[tuple[str, str]] = []
        duplicate_subject_ids: list[tuple[str, str]] = []

        def index_entries(
            label: str,
            values: tuple[StructuredEntry, ...],
        ) -> dict[str, StructuredEntry | Subject | ReconciliationRecord]:
            duplicates: list[str] = []
            indexed = _by_id(values, duplicate_ids=duplicates)
            duplicate_entry_ids.extend((label, value) for value in duplicates)
            return indexed

        base_entries = index_entries("merge base", base_entry_units)
        head_entries = index_entries("HEAD", head_entry_units)
        target_entries = index_entries(target_ref, target_entry_units)

        def index_subjects(
            label: str,
            values: tuple[Subject, ...],
        ) -> dict[str, StructuredEntry | Subject | ReconciliationRecord]:
            duplicates: list[str] = []
            indexed = _by_id(values, duplicate_ids=duplicates)
            duplicate_subject_ids.extend((label, value) for value in duplicates)
            return indexed

        base_subjects = index_subjects("merge base", base_subject_units)
        head_subjects = index_subjects("HEAD", head_subject_units)
        target_subjects = index_subjects(target_ref, target_subject_units)
        changed_head_records = _changed(_by_id(base_records), _by_id(head_records))
        changed_target_records = _changed(_by_id(base_records), _by_id(target_records))
        resolution_records = (*changed_head_records.values(), *changed_target_records.values())
        head_changed_files = _changed_files(project_root, base, "HEAD")
        target_changed_files = _changed_files(project_root, base, target_ref)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return MergeReviewResult(
            "Merge review unavailable: " + str(exc) + "\nConflict-free status was not established.",
            True,
        )

    left_entries = _changed(base_entries, head_entries)
    right_entries = _changed(base_entries, target_entries)
    left_deleted = _changed(base_entries, head_entries, include_deleted=True)
    right_deleted = _changed(base_entries, target_entries, include_deleted=True)
    left_subjects = _changed(base_subjects, head_subjects)
    right_subjects = _changed(base_subjects, target_subjects)
    conflicts: list[str] = []
    reviews: list[str] = []
    for label, entry_id in duplicate_entry_ids:
        conflicts.append(
            f"MC-MERGE-006 {label} has duplicate Entry ID {entry_id}; "
            "canonical lookup is unsafe"
        )
    for label, subject_id in duplicate_subject_ids:
        conflicts.append(
            f"MC-MERGE-006 {label} has duplicate Subject ID {subject_id}; "
            "canonical lookup is unsafe"
        )
    for side, issues in (("HEAD", head_subject_issues), (target_ref, target_subject_issues)):
        for issue in issues:
            conflicts.append(f"MC-MERGE-006 {side} has invalid Subject registry: {issue}")
    for side, issues in (("HEAD", head_record_issues), (target_ref, target_record_issues)):
        for issue in issues:
            identity = f" {issue.record_id}" if issue.record_id else ""
            conflicts.append(
                f"MC-MERGE-006 {side} has invalid reconciliation{identity}: {issue.message}"
            )
    # The merge base is historical input, so an Entry issue there may have
    # been repaired (or removed) independently on both sides.  Only the two
    # result snapshots are authoritative for integrity blockers; an invalid
    # Entry that survives on either side is still reported below.
    for side, issues in (("HEAD", head_entry_issues), (target_ref, target_entry_issues)):
        for issue in issues:
            conflicts.append(f"MC-MERGE-006 {side} has invalid Entry: {issue}")

    base_subject_ids = set(base_subjects)
    new_head_custom_subjects = {
        key: subject for key, subject in head_subjects.items()
        if key not in base_subject_ids and subject.status == "active" and not subject.canonical_ref
    }
    new_target_custom_subjects = {
        key: subject for key, subject in target_subjects.items()
        if key not in base_subject_ids and subject.status == "active" and not subject.canonical_ref
    }

    left_refs: dict[str, str] = {}
    left_aliases: dict[str, str] = {}
    for subject in left_subjects.values():
        if subject.status != "active":
            continue
        if subject.canonical_ref:
            try:
                left_refs[normalize_canonical_ref(subject.canonical_ref)] = subject.subject_id
            except ValueError:
                pass
        for alias in (subject.title, *subject.aliases):
            left_aliases[normalize_alias(alias)] = subject.subject_id
    for subject in right_subjects.values():
        if subject.status != "active":
            continue
        if subject.canonical_ref:
            try:
                normalized = normalize_canonical_ref(subject.canonical_ref)
                owner = left_refs.get(normalized)
                if owner and owner.casefold() != subject.subject_id.casefold():
                    conflicts.append(f"MC-MERGE-001 duplicate Canonical-Ref {normalized}: {owner}, {subject.subject_id}")
            except ValueError:
                pass
        collision = next((left_aliases.get(normalize_alias(alias)) for alias in (subject.title, *subject.aliases) if left_aliases.get(normalize_alias(alias))), None)
        if collision and collision.casefold() != subject.subject_id.casefold():
            conflicts.append(f"MC-MERGE-002 exact alias collision: {collision}, {subject.subject_id}")
        if (
            subject.subject_id.casefold() in new_target_custom_subjects
            and new_head_custom_subjects
            and not subject.canonical_ref
            and not collision
            and any(
                key != subject.subject_id.casefold()
                for key in new_head_custom_subjects
            )
        ):
            reviews.append("MC-MERGE-REVIEW-003 both branches created differently named custom Subjects")

    def identity(entry: StructuredEntry) -> tuple[str, str, str] | None:
        subject = entry.fields.get("Subject")
        facet = entry.fields.get("Facet")
        if entry.status != "active" or not subject or not facet:
            return None
        return entry.scope.casefold(), subject.casefold(), facet.casefold()

    left_identities = {identity(entry): entry for entry in left_entries.values() if identity(entry)}
    right_identities = {identity(entry): entry for entry in right_entries.values() if identity(entry)}
    for key in sorted(set(left_identities) & set(right_identities)):
        left = left_identities[key]
        right = right_identities[key]
        if left.entry_id.casefold() != right.entry_id.casefold() or left.text != right.text:
            conflicts.append(
                f"MC-MERGE-003 concurrent structural owner {key}: {left.entry_id}, {right.entry_id}"
            )

    for deleted, changed, label in (
        (left_deleted, right_entries, "HEAD deletion while target changes"),
        (right_deleted, left_entries, "target deletion while HEAD changes"),
    ):
        for entry_id, marker in deleted.items():
            if entry_id in changed:
                reviews.append(
                    f"MC-MERGE-REVIEW-006 {label}: {marker.entry_id}"
                )

    resolved_pairs = {
        pair for record in resolution_records for pair in reconciliation_pairs(record)
    }

    def reconciled(left: StructuredEntry, right: StructuredEntry) -> bool:
        pair = frozenset({left.entry_id.casefold(), right.entry_id.casefold()})
        if pair in resolved_pairs:
            return True
        return (
            left.fields.get("Exception-To", "").casefold() == right.entry_id.casefold()
            or right.fields.get("Exception-To", "").casefold() == left.entry_id.casefold()
        )

    for left in left_entries.values():
        for right in right_entries.values():
            if left.path.as_posix() == right.path.as_posix() and identity(left) != identity(right) and not reconciled(left, right):
                reviews.append(
                    f"MC-MERGE-REVIEW-001 concurrent hard-memory changes in {left.path.as_posix()}"
                )
            left_subject = left.fields.get("Subject", "").casefold()
            right_subject = right.fields.get("Subject", "").casefold()
            if left_subject and left_subject == right_subject and left.fields.get("Facet") != right.fields.get("Facet") and not reconciled(left, right):
                reviews.append(
                    f"MC-MERGE-REVIEW-002 concurrent changes to different facets of Subject {left.fields.get('Subject')}"
                )
            if left.scope == "project" and right.scope.startswith("area:") and left.entry_id.split("-", 2)[1].upper() == "CON" and not reconciled(left, right):
                reviews.append("MC-MERGE-REVIEW-004 project constraint and area constraint changed concurrently")
            if right.scope == "project" and left.scope.startswith("area:") and right.entry_id.split("-", 2)[1].upper() == "CON" and not reconciled(left, right):
                reviews.append("MC-MERGE-REVIEW-004 project constraint and area constraint changed concurrently")

    relation_fields = ("Supersedes", "Superseded-By", "Exception-To", "Promoted-From", "Promoted-To")
    for superseding, extending, label in (
        (left_entries, right_entries, "HEAD supersedes while target extends"),
        (right_entries, left_entries, "target supersedes while HEAD extends"),
    ):
        for previous in superseding.values():
            if previous.status != "superseded" and not previous.fields.get("Superseded-By"):
                continue
            old_id = previous.entry_id.casefold()
            for entry in extending.values():
                references_old = any(entry.fields.get(field, "").casefold() == old_id for field in relation_fields)
                if (entry.entry_id.casefold() == old_id and entry.status == "active") or references_old:
                    conflicts.append(
                        f"MC-MERGE-004 {label}: {previous.entry_id}, {entry.entry_id}"
                    )

    for merged_subjects, other_entries, label in (
        (left_subjects, right_entries, "HEAD merges while target extends"),
        (right_subjects, left_entries, "target merges while HEAD extends"),
    ):
        for subject in merged_subjects.values():
            if subject.status != "merged":
                continue
            for entry in other_entries.values():
                if entry.status == "active" and entry.fields.get("Subject", "").casefold() == subject.subject_id.casefold():
                    conflicts.append(
                        f"MC-MERGE-005 {label}: {subject.subject_id}, {entry.entry_id}"
                    )

    def evidence_paths(entry: StructuredEntry) -> set[str]:
        result: set[str] = set()
        for evidence in entry.evidence:
            prefix, separator, remainder = evidence.partition(":")
            if separator and prefix in {"repo", "doc", "test"}:
                result.add(remainder.partition("@")[0])
        return result

    for entries, other_files, label in (
        (left_entries, target_changed_files, "target"),
        (right_entries, head_changed_files, "HEAD"),
    ):
        for entry in entries.values():
            overlap = sorted(evidence_paths(entry) & other_files)
            if overlap:
                reviews.append(
                    f"MC-MERGE-REVIEW-005 {entry.entry_id} Evidence changed on {label}: {', '.join(overlap)}"
                )

    conflicts = sorted(set(conflicts))
    reviews = sorted(set(reviews))
    if conflicts:
        status = "CONFLICT"
    elif reviews:
        status = "REVIEW"
    else:
        status = "CLEAR"
    lines = [f"Merge review status: {status}", f"Merge base: {base}"]
    lines.extend(f"- {item}" for item in conflicts)
    lines.extend(f"- {item}: Concurrent hard-memory changes require semantic reconciliation." for item in reviews)
    if status == "CLEAR":
        lines.append("- No deterministic conflict or configured reconciliation risk was detected; this is not a semantic-consistency proof.")
    return MergeReviewResult("\n".join(lines), bool(conflicts))
