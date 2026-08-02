"""Strict Protocol 0.7 reconciliation-record parsing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .entries import ENTRY_ID_RE


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
