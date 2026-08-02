"""Strict Protocol 0.7 reconciliation-record parsing."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import re

from .entries import ENTRY_ID_RE, StructuredEntry
from .structural import (
    active_structural_operand_issues,
    structural_identity,
    subject_index,
)
from .subjects import Subject


REC_ID_RE = re.compile(r"^## (MC-REC-\d{8}-[0-9a-f]{8})\s+—\s+(.+)$", re.I)
RESOLUTIONS = frozenset({"distinct", "superseded", "exception", "subject-merged"})


@dataclass(frozen=True)
class ReconciliationRecord:
    record_id: str
    title: str
    status: str
    resolution: str
    entries: tuple[str, ...]
    evidence: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class ReconciliationIssue:
    message: str
    record_id: str = ""
    entries: tuple[str, ...] = ()


def reconciliation_pairs(
    record: ReconciliationRecord,
) -> tuple[frozenset[str], ...]:
    """Return only the exact Entry pairs acknowledged by a valid record."""

    return tuple(
        frozenset((left.casefold(), right.casefold()))
        for left, right in combinations(record.entries, 2)
    )


def _admissible_evidence(value: str) -> bool:
    if value in {"user-confirmed", "legacy-unverified"}:
        return True
    prefix, separator, remainder = value.partition(":")
    return bool(separator and remainder and prefix in {"repo", "doc", "test", "issue", "pr", "migration"})


def parse_reconciliations(
    path: Path,
    text: str,
) -> tuple[tuple[ReconciliationRecord, ...], tuple[str, ...]]:
    """Parse every H2 record, returning valid records and deterministic issues."""

    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    records: list[ReconciliationRecord] = []
    issues: list[str] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        section_lines = lines[start:end]
        section = "\n".join(section_lines).strip()
        heading = REC_ID_RE.fullmatch(section_lines[0])
        if not heading:
            issues.append(f"{path.name}: malformed reconciliation heading {section_lines[0]!r}")
            continue

        record_id, title = heading.groups()
        scalars: dict[str, str] = {}
        blocks: dict[str, list[str]] = {"Entries": [], "Evidence": []}
        seen_blocks: set[str] = set()
        active_block: str | None = None
        record_issues: list[str] = []
        for line in section_lines[1:]:
            if not line.strip():
                continue
            field = re.fullmatch(r"([A-Za-z][A-Za-z-]*):\s*(.*)", line)
            if field:
                key, value = field.groups()
                active_block = None
                if key in {"Status", "Resolution"}:
                    if key in scalars:
                        record_issues.append(f"duplicate {key} field")
                    scalars[key] = value.strip()
                elif key in blocks:
                    if value.strip():
                        record_issues.append(f"{key} block heading must not contain a value")
                    if key in seen_blocks:
                        record_issues.append(f"duplicate {key} block")
                    seen_blocks.add(key)
                    active_block = key
                else:
                    record_issues.append(f"unknown field {key}")
                continue
            if line.startswith("- ") and active_block:
                blocks[active_block].append(line[2:].strip())
                continue
            record_issues.append(f"unexpected line {line!r}")

        entries = tuple(blocks["Entries"])
        evidence = tuple(blocks["Evidence"])
        canonical_entries = tuple(sorted(set(entries), key=str.casefold))
        if scalars.get("Status") != "active":
            record_issues.append("Status must be active")
        if scalars.get("Resolution") not in RESOLUTIONS:
            record_issues.append("Resolution is missing or invalid")
        if "Entries" not in seen_blocks or len(entries) < 2:
            record_issues.append("Entries must reference at least two Entry IDs")
        if entries != canonical_entries:
            record_issues.append("Entries must be unique and canonically sorted")
        if any(ENTRY_ID_RE.fullmatch(value) is None for value in entries):
            record_issues.append("Entries contains an invalid Entry ID")
        if "Evidence" not in seen_blocks or not evidence or not all(_admissible_evidence(item) for item in evidence):
            record_issues.append("Evidence is missing or invalid")
        if record_issues:
            issues.append(f"{record_id}: " + "; ".join(dict.fromkeys(record_issues)))
            continue
        records.append(ReconciliationRecord(
            record_id,
            title,
            scalars["Status"],
            scalars["Resolution"],
            entries,
            evidence,
            section,
        ))
    return tuple(records), tuple(issues)


def validate_reconciliations(
    records: tuple[ReconciliationRecord, ...],
    parse_issues: tuple[str, ...],
    entries: tuple[StructuredEntry, ...],
    subjects: tuple[Subject, ...],
) -> tuple[tuple[ReconciliationRecord, ...], tuple[ReconciliationIssue, ...]]:
    """Validate records against one complete repository revision.

    Only records returned in the first tuple are safe to use as review
    acknowledgements.  This keeps current-worktree and merge review on the
    same relation-consistency rules.
    """

    by_id: dict[str, list[StructuredEntry]] = {}
    for entry in entries:
        by_id.setdefault(entry.entry_id.casefold(), []).append(entry)
    subjects_by_id = subject_index(subjects)
    issues = [ReconciliationIssue(issue) for issue in parse_issues]
    valid_records: list[ReconciliationRecord] = []
    identities: set[tuple[str, ...]] = set()
    record_ids: set[str] = set()

    for record in records:
        duplicate_id = record.record_id.casefold() in record_ids
        record_ids.add(record.record_id.casefold())
        identity = tuple(value.casefold() for value in record.entries)
        duplicate_identity = identity in identities
        identities.add(identity)
        resolved = [
            by_id[value.casefold()][0]
            for value in record.entries
            if len(by_id.get(value.casefold(), ())) == 1
        ]
        missing_or_duplicate = len(resolved) != len(record.entries)
        relation_valid = True
        relationship_resolution = record.resolution in {
            "superseded", "exception", "subject-merged",
        }
        if relationship_resolution and len(record.entries) != 2:
            relation_valid = False
        elif record.resolution == "superseded":
            relation_valid = any(
                left.status == "superseded"
                and right.status == "active"
                and left.fields.get("Superseded-By", "").casefold() == right.entry_id.casefold()
                and right.fields.get("Supersedes", "").casefold() == left.entry_id.casefold()
                for left in resolved for right in resolved if left is not right
            )
        elif record.resolution == "exception":
            relation_valid = any(
                not active_structural_operand_issues(left, subjects_by_id)
                and not active_structural_operand_issues(right, subjects_by_id)
                and left.fields.get("Exception-To", "").casefold() == right.entry_id.casefold()
                and left.scope.startswith("area:")
                and right.scope == "project"
                and not right.fields.get("Exception-To")
                and left.fields.get("Subject", "").casefold()
                == right.fields.get("Subject", "").casefold()
                and left.fields.get("Facet", "").casefold()
                == right.fields.get("Facet", "").casefold()
                for left in resolved for right in resolved if left is not right
            )
        elif record.resolution == "subject-merged":
            relation_valid = any(
                len(subjects_by_id.get(left.fields.get("Subject", "").casefold(), ())) == 1
                and getattr(
                    subjects_by_id[left.fields.get("Subject", "").casefold()][0],
                    "status",
                    "",
                ) == "merged"
                and getattr(
                    subjects_by_id[left.fields.get("Subject", "").casefold()][0],
                    "merged_into",
                    "",
                ).casefold() == right.fields.get("Subject", "").casefold()
                and len(subjects_by_id.get(right.fields.get("Subject", "").casefold(), ())) == 1
                and subjects_by_id[right.fields.get("Subject", "").casefold()][0].status == "active"
                for left in resolved for right in resolved if left is not right
            )

        distinct_valid = True
        if record.resolution == "distinct" and not missing_or_duplicate:
            structural_identities: list[tuple[str, str, str]] = []
            for entry in resolved:
                if active_structural_operand_issues(entry, subjects_by_id):
                    distinct_valid = False
                    break
                structural_identities.append(structural_identity(entry))
            if len(set(structural_identities)) != len(structural_identities):
                distinct_valid = False

        reasons: list[str] = []
        if duplicate_id:
            reasons.append("duplicate reconciliation record ID")
        if duplicate_identity:
            reasons.append("duplicate active reconciliation identity")
        if missing_or_duplicate:
            reasons.append("referenced Entry IDs must each resolve exactly once")
        if relationship_resolution and len(record.entries) != 2:
            reasons.append(
                f"{record.resolution} resolution requires exactly two Entry IDs"
            )
        if not relation_valid and not (
            relationship_resolution and len(record.entries) != 2
        ):
            reasons.append(f"{record.resolution} resolution is inconsistent with current relations")
        if not distinct_valid:
            reasons.append(
                "distinct resolution requires active entries with different "
                "Scope + Subject + Facet identities; change identity or lifecycle relations"
            )
        if reasons:
            issues.append(ReconciliationIssue(
                "; ".join(reasons), record.record_id, record.entries,
            ))
        else:
            valid_records.append(record)

    return tuple(valid_records), tuple(issues)
