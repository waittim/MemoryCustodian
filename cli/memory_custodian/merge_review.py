"""Best-effort, read-only Git merge reconciliation review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .entries import StructuredEntry, parse_structured_entries
from .reconciliations import ReconciliationRecord, parse_reconciliations
from .subjects import Subject, normalize_alias, normalize_canonical_ref, parse_subjects


@dataclass(frozen=True)
class MergeReviewResult:
    text: str
    blocking: bool


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
    except ValueError:
        return ""


def _files(project_root: Path, revision: str, memory_relative: str) -> tuple[str, ...]:
    output = _git(project_root, "ls-tree", "-r", "--name-only", revision, "--", memory_relative)
    return tuple(sorted(
        line for line in output.splitlines()
        if line.endswith(".md") and (
            line.endswith(("constraints.md", "decisions.md", "do-not-use.md", "subjects.md", "reconciliations.md"))
            or f"/{memory_relative.strip('/')}/areas/" in f"/{line}"
            or line.startswith(memory_relative.rstrip("/") + "/areas/")
        )
    ))


def _entries(project_root: Path, revision: str, files: tuple[str, ...]) -> dict[str, StructuredEntry]:
    result: dict[str, StructuredEntry] = {}
    for relative in files:
        if relative.endswith(("subjects.md", "reconciliations.md")):
            continue
        text = _show(project_root, revision, relative)
        for entry in parse_structured_entries(Path(relative), text):
            result[entry.entry_id.casefold()] = entry
    return result


def _subjects(project_root: Path, revision: str, registry: str) -> dict[str, Subject]:
    return {
        item.subject_id.casefold(): item
        for item in parse_subjects(Path(registry), _show(project_root, revision, registry))
    }


def _reconciliations(project_root: Path, revision: str, relative: str) -> tuple[ReconciliationRecord, ...]:
    records, _issues = parse_reconciliations(
        Path(relative), _show(project_root, revision, relative)
    )
    return records


def _changed(base: dict[str, object], side: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in side.items() if key not in base or getattr(base[key], "text") != getattr(value, "text")}


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
        base_entries = _entries(project_root, base, all_files)
        head_entries = _entries(project_root, "HEAD", all_files)
        target_entries = _entries(project_root, target_ref, all_files)
        base_subjects = _subjects(project_root, base, registry)
        head_subjects = _subjects(project_root, "HEAD", registry)
        target_subjects = _subjects(project_root, target_ref, registry)
        resolution_records = (
            *_reconciliations(project_root, "HEAD", reconciliations),
            *_reconciliations(project_root, target_ref, reconciliations),
        )
        head_changed_files = _changed_files(project_root, base, "HEAD")
        target_changed_files = _changed_files(project_root, base, target_ref)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return MergeReviewResult(
            "Merge review unavailable: " + str(exc) + "\nConflict-free status was not established.",
            False,
        )

    left_entries = _changed(base_entries, head_entries)
    right_entries = _changed(base_entries, target_entries)
    left_subjects = _changed(base_subjects, head_subjects)
    right_subjects = _changed(base_subjects, target_subjects)
    conflicts: list[str] = []
    reviews: list[str] = []

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
        if left_subjects and not subject.canonical_ref and not collision and subject.subject_id.casefold() not in left_subjects:
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

    resolved_identities = {
        frozenset(value.casefold() for value in record.entries)
        for record in resolution_records
    }

    def reconciled(left: StructuredEntry, right: StructuredEntry) -> bool:
        pair = frozenset({left.entry_id.casefold(), right.entry_id.casefold()})
        if any(pair <= identity for identity in resolved_identities):
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
