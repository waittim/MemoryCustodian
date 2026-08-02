"""Shared validation for active structural conflict operands."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .entries import StructuredEntry, VALID_SCOPES_RE
from .subjects import FACETS, Subject


@dataclass(frozen=True)
class StructuralOperandIssue:
    field: str
    message: str


def subject_index(subjects: Iterable[Subject]) -> dict[str, tuple[Subject, ...]]:
    grouped: dict[str, list[Subject]] = {}
    for subject in subjects:
        grouped.setdefault(subject.subject_id.casefold(), []).append(subject)
    return {key: tuple(values) for key, values in grouped.items()}


def active_structural_operand_issues(
    entry: StructuredEntry,
    subjects: dict[str, tuple[Subject, ...]],
) -> tuple[StructuralOperandIssue, ...]:
    issues: list[StructuralOperandIssue] = []
    if entry.status != "active":
        issues.append(StructuralOperandIssue("Status", "Entry must be active."))
    if VALID_SCOPES_RE.fullmatch(entry.scope) is None:
        issues.append(StructuralOperandIssue("Scope", f"Invalid Scope {entry.scope!r}."))

    subject_id = entry.fields.get("Subject", "")
    matches = subjects.get(subject_id.casefold(), ()) if subject_id else ()
    if len(matches) != 1 or matches[0].status != "active":
        issues.append(StructuralOperandIssue(
            "Subject",
            "Subject must resolve exactly once to an active registry entry.",
        ))

    facet = entry.fields.get("Facet", "")
    if facet not in FACETS:
        issues.append(StructuralOperandIssue("Facet", f"Invalid Facet {facet!r}."))
    return tuple(issues)


def structural_identity(entry: StructuredEntry) -> tuple[str, str, str]:
    return (
        entry.scope.casefold(),
        entry.fields.get("Subject", "").casefold(),
        entry.fields.get("Facet", "").casefold(),
    )
