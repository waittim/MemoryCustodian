"""Protocol 0.6 entry identity, evidence, parsing, and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
import re
import uuid

ENTRY_SCHEMA_VERSION = "1"
TYPE_CODES = {
    "decision": "DEC",
    "constraint": "CON",
    "tombstone": "DNU",
    "do-not-use": "DNU",
    "preference": "PREF",
    "area": "AREA",
    "rule": "AREA",
    "profile": "AREA",
    "inbox": "INBOX",
    "candidate": "INBOX",
}
ENTRY_ID_RE = re.compile(r"\bMC-(DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-(\d{8})-([0-9a-f]{8})\b", re.I)
ACTIVE_EVIDENCE_RE = re.compile(
    r"^(?:user-confirmed|(?:repo|doc|test):[^@\s]+(?:@[A-Za-z0-9._-]+)?|issue:#\d+|pr:#\d+)$"
)
CANDIDATE_ONLY_EVIDENCE = {"agent-observed", "conversation-unconfirmed"}
INTERNAL_EVIDENCE = {"legacy-unverified"}
VALID_SCOPES_RE = re.compile(r"^(?:project|area:[A-Za-z0-9][A-Za-z0-9._-]*)$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z-]*):(?:\s*(.*))?$")


@dataclass(frozen=True)
class StructuredEntry:
    entry_id: str
    title: str
    status: str
    scope: str
    evidence: tuple[str, ...]
    text: str
    path: Path
    fields: dict[str, str]
    field_counts: dict[str, int] = field(default_factory=dict)
    field_bodies: dict[str, str] = field(default_factory=dict)


TYPED_BODY_FIELDS = {
    "Decision",
    "Constraint",
    "Rejected",
    "Preference",
    "Rule",
    "Profile",
    "Statement",
}
LIFECYCLE_FIELDS = {
    "Supersedes",
    "Superseded-By",
    "Promoted-From",
    "Promoted-To",
}


def generate_entry_id(kind: str, existing_ids: set[str] | None = None, *, day: date | None = None) -> str:
    code = TYPE_CODES[kind]
    used = {value.casefold() for value in (existing_ids or set())}
    stamp = (day or date.today()).strftime("%Y%m%d")
    while True:
        value = f"MC-{code}-{stamp}-{uuid.uuid4().hex[:8]}"
        if value.casefold() not in used:
            return value


def entry_ids(text: str) -> list[str]:
    return [match.group(0) for match in ENTRY_ID_RE.finditer(text)]


def heading_entry_ids(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            match = ENTRY_ID_RE.search(line)
            if match:
                found.append(match.group(0))
    return found


def memory_entry_ids(memory_dir: Path) -> set[str]:
    found: set[str] = set()
    if not memory_dir.exists():
        return found
    for path in memory_dir.rglob("*.md"):
        for value in heading_entry_ids(path.read_text(encoding="utf-8")):
            found.add(value)
    return found


def _safe_source_path(value: str) -> tuple[str, str | None]:
    raw_path, separator, revision = value.partition("@")
    normalized = raw_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise ValueError(f"Evidence path must be a safe project-relative path: {raw_path!r}")
    return normalized, revision if separator else None


def validate_evidence(
    evidence: list[str] | tuple[str, ...],
    project_root: Path,
    *,
    candidate: bool = False,
    allow_missing: bool = False,
    allow_internal: bool = False,
) -> tuple[str, ...]:
    project_root = project_root.resolve()
    if not evidence:
        raise ValueError("Protocol 0.6 active memory requires at least one --evidence value.")
    validated: list[str] = []
    for raw in evidence:
        value = raw.strip()
        if value in CANDIDATE_ONLY_EVIDENCE:
            if not candidate:
                raise ValueError(
                    f"{value} evidence cannot create active memory. "
                    "Use --candidate or provide user-confirmed/source-backed evidence."
                )
            validated.append(value)
            continue
        if value in INTERNAL_EVIDENCE:
            if not allow_internal:
                raise ValueError("legacy-unverified evidence is reserved for migration.")
            validated.append(value)
            continue
        if not ACTIVE_EVIDENCE_RE.fullmatch(value):
            raise ValueError(f"Invalid evidence: {value!r}")
        prefix, separator, rest = value.partition(":")
        if separator and prefix in {"repo", "doc", "test"}:
            source_path, revision = _safe_source_path(rest)
            target = (project_root / source_path).resolve()
            try:
                target.relative_to(project_root)
            except ValueError as exc:
                raise ValueError(f"Evidence path escapes the project: {source_path!r}") from exc
            if not target.exists() and not allow_missing:
                raise ValueError(
                    f"Evidence path does not exist: {source_path}. Use --allow-missing-evidence to retain it anyway."
                )
            value = f"{prefix}:{source_path}" + (f"@{revision}" if revision else "")
        validated.append(value)
    if not candidate and all(value in CANDIDATE_ONLY_EVIDENCE for value in validated):
        raise ValueError(
            "Unconfirmed evidence cannot create active memory. "
            "Use --candidate or provide user-confirmed/source-backed evidence."
        )
    return tuple(validated)


def validate_scope(scope: str) -> str:
    if not VALID_SCOPES_RE.fullmatch(scope):
        raise ValueError(f"Invalid Scope: {scope!r}")
    return scope


def render_active_entry(
    kind: str,
    entry_id: str,
    title: str,
    message: str,
    reason: str | None,
    scope: str,
    evidence: tuple[str, ...],
    *,
    subject: str | None = None,
    facet: str | None = None,
    supersedes: str | None = None,
) -> str:
    labels = {
        "decision": "Decision",
        "constraint": "Constraint",
        "preference": "Preference",
        "tombstone": "Rejected",
        "do-not-use": "Rejected",
        "area": "Decision",
        "rule": "Rule",
        "profile": "Profile",
    }
    lines = [
        f"## {entry_id} — {'Tombstone: ' if kind in {'tombstone', 'do-not-use'} else ''}{title}",
        "",
        "Status: active",
        f"Scope: {scope}",
    ]
    if subject:
        lines.append(f"Subject: {subject}")
    if facet:
        lines.append(f"Facet: {facet}")
    lines.extend(["Evidence:", *(f"- {item}" for item in evidence)])
    if supersedes:
        lines.extend([f"Supersedes: {supersedes}"])
    lines.extend(["", f"{labels[kind]}:", message])
    if reason:
        lines.extend(["", "Reason:", reason])
    return "\n".join(lines)


def render_candidate_entry(
    entry_id: str,
    title: str,
    candidate_type: str,
    message: str,
    scope: str,
    evidence: tuple[str, ...],
    note: str | None,
    *,
    subject: str | None = None,
    facet: str | None = None,
) -> str:
    lines = [
        f"## {entry_id} — {title}",
        "",
        "Status: candidate",
        f"Candidate-Type: {candidate_type}",
        f"Scope: {scope}",
    ]
    if subject:
        lines.append(f"Provisional-Subject: {subject}")
    if facet:
        lines.append(f"Provisional-Facet: {facet}")
    lines.extend([
        "Evidence:",
        *(f"- {item}" for item in evidence),
        "",
        "Statement:",
        message,
        "",
        "Promotion-Requirement:",
        note or "Confirm with the user or an authoritative project source.",
    ])
    return "\n".join(lines)


def split_h2(text: str) -> tuple[str, list[str]]:
    matches = list(re.finditer(r"(?m)^## .*$", text))
    if not matches:
        return text, []
    preamble = text[: matches[0].start()].rstrip()
    entries = [
        text[match.start() : (matches[index + 1].start() if index + 1 < len(matches) else len(text))].strip()
        for index, match in enumerate(matches)
    ]
    return preamble, entries


def parse_structured_entries(path: Path, text: str) -> list[StructuredEntry]:
    _preamble, sections = split_h2(text)
    parsed: list[StructuredEntry] = []
    for section in sections:
        lines = section.splitlines()
        heading = ENTRY_ID_RE.search(lines[0])
        if not heading:
            continue
        fields: dict[str, str] = {}
        field_counts: dict[str, int] = {}
        occurrence_bodies: dict[str, list[list[str]]] = {}
        evidence: list[str] = []
        current_field: str | None = None
        current_body: list[str] = []

        def flush_field() -> None:
            nonlocal current_field, current_body
            if current_field is not None:
                occurrence_bodies.setdefault(current_field, []).append(current_body)
            current_field = None
            current_body = []

        for line in lines[1:]:
            matched_field = FIELD_RE.match(line)
            if matched_field:
                flush_field()
                key, value = matched_field.group(1), matched_field.group(2) or ""
                fields[key] = value
                field_counts[key] = field_counts.get(key, 0) + 1
                current_field = key
                current_body = [value] if value.strip() else []
                continue
            if current_field == "Evidence" and line.startswith("- "):
                evidence.append(line[2:].strip())
                current_body.append(line[2:].strip())
            elif current_field is not None and line.strip():
                current_body.append(line.strip())
        flush_field()
        field_bodies = {
            key: "\n".join(
                line
                for occurrence in occurrences
                for line in occurrence
                if line.strip()
            ).strip()
            for key, occurrences in occurrence_bodies.items()
        }
        title = re.sub(r"^.*?\s+—\s+", "", lines[0]).strip()
        parsed.append(
            StructuredEntry(
                heading.group(0),
                title,
                fields.get("Status", ""),
                fields.get("Scope", ""),
                tuple(evidence),
                section,
                path,
                fields,
                field_counts,
                field_bodies,
            )
        )
    return parsed


def expected_typed_body(entry: StructuredEntry, relative_path: str) -> str | None:
    code = entry.entry_id.split("-", 2)[1].upper()
    if code == "DEC":
        return "Decision"
    if code == "CON":
        return "Constraint"
    if code in {"DNU", "TOMB"}:
        return "Rejected"
    if code == "PREF":
        return "Preference"
    if code == "INBOX":
        return "Statement"
    if code == "AREA":
        if relative_path.startswith("rules/"):
            return "Rule"
        if relative_path.startswith("profiles/"):
            return "Profile"
        return "Decision"
    return None


def structured_entry_schema_issues(
    entry: StructuredEntry,
    relative_path: str,
) -> list[str]:
    """Validate the declared Protocol 0.6 structure of one formal entry."""

    issues: list[str] = []
    prefix = f"{relative_path}: {entry.entry_id}"
    for name in ("Status", "Scope", "Evidence"):
        count = entry.field_counts.get(name, 0)
        if count != 1:
            issues.append(f"{prefix} must declare exactly one {name} field (found {count})")

    for name, count in sorted(entry.field_counts.items()):
        if count > 1:
            issues.append(f"{prefix} has duplicate {name} fields")

    expected_body = expected_typed_body(entry, relative_path)
    if expected_body is not None:
        count = entry.field_counts.get(expected_body, 0)
        if count != 1:
            issues.append(
                f"{prefix} must declare exactly one {expected_body} typed body "
                f"(found {count})"
            )
        elif not entry.field_bodies.get(expected_body, "").strip():
            issues.append(f"{prefix} has an empty {expected_body} typed body")
        for body_name in sorted(TYPED_BODY_FIELDS - {expected_body}):
            if entry.field_counts.get(body_name, 0):
                issues.append(
                    f"{prefix} uses {body_name} body but its Entry ID/storage "
                    f"requires {expected_body}"
                )

    superseded_by = bool(entry.fields.get("Superseded-By"))
    promoted_to = bool(entry.fields.get("Promoted-To"))
    if superseded_by and promoted_to:
        issues.append(
            f"{prefix} cannot declare both Superseded-By and Promoted-To"
        )
    if entry.status == "active" and (superseded_by or promoted_to):
        issues.append(f"{prefix} active lifecycle conflicts with terminal relation fields")
    if entry.status == "candidate" and any(
        entry.fields.get(name) for name in LIFECYCLE_FIELDS
    ):
        issues.append(f"{prefix} candidate lifecycle cannot declare transition relations")
    if entry.status == "superseded" and promoted_to:
        issues.append(f"{prefix} superseded lifecycle cannot declare Promoted-To")
    if entry.status == "promoted" and superseded_by:
        issues.append(f"{prefix} promoted lifecycle cannot declare Superseded-By")

    if entry.status in {"candidate", "promoted"}:
        candidate_type_count = entry.field_counts.get("Candidate-Type", 0)
        if candidate_type_count != 1:
            issues.append(
                f"{prefix} must declare exactly one Candidate-Type field "
                f"(found {candidate_type_count})"
            )
    elif entry.field_counts.get("Candidate-Type", 0):
        issues.append(
            f"{prefix} non-candidate lifecycle cannot declare Candidate-Type"
        )
    return issues


def structured_entry_storage_issues(
    entry: StructuredEntry,
    relative_path: str,
) -> list[str]:
    """Validate canonical Entry ID, storage path, and Scope relationships."""

    if relative_path.startswith("archive/"):
        return []

    issues: list[str] = []
    prefix = f"{relative_path}: {entry.entry_id}"
    code = entry.entry_id.split("-", 2)[1].upper()
    project_files = {
        "decisions.md": {"DEC"},
        "constraints.md": {"CON"},
        "do-not-use.md": {"DNU", "TOMB"},
        "preferences.md": {"PREF"},
    }

    if relative_path == "inbox.md":
        if code != "INBOX":
            issues.append(f"{prefix} type does not match its storage location")
        return issues

    if code == "INBOX":
        issues.append(f"{prefix} must be stored in inbox.md")
        return issues

    expected_codes = project_files.get(relative_path)
    if expected_codes is not None:
        if code not in expected_codes:
            issues.append(f"{prefix} type does not match its storage location")
        if entry.scope != "project":
            issues.append(f"{prefix} project storage requires Scope: project")
        return issues

    if relative_path.startswith("areas/") and relative_path.endswith(".md"):
        area_name = relative_path[len("areas/") : -len(".md")]
        if "/" in area_name or not area_name:
            issues.append(f"{prefix} has a non-canonical area storage path")
            return issues
        if code not in {"AREA", "CON", "PREF", "DNU"}:
            issues.append(f"{prefix} type does not match its area storage location")
        expected_scope = f"area:{area_name}"
        if entry.scope != expected_scope:
            issues.append(
                f"{prefix} must use Scope: {expected_scope} for {relative_path}"
            )
        return issues

    if relative_path.startswith("rules/") and relative_path.endswith(".md"):
        if code != "AREA":
            issues.append(f"{prefix} type does not match its rule storage location")
        if entry.scope != "project":
            issues.append(f"{prefix} rule storage requires Scope: project")
        return issues

    if relative_path.startswith("profiles/") and relative_path.endswith(".md"):
        if code != "AREA":
            issues.append(f"{prefix} type does not match its profile storage location")
        if entry.scope != "project":
            issues.append(f"{prefix} profile storage requires Scope: project")
        return issues

    issues.append(f"{prefix} formal entry is outside a canonical storage file")
    return issues


def supersede_entry(text: str, old_id: str, new_id: str) -> str:
    preamble, sections = split_h2(text)
    changed = False
    updated: list[str] = []
    for section in sections:
        match = ENTRY_ID_RE.search(section.splitlines()[0])
        if not match or match.group(0).casefold() != old_id.casefold():
            updated.append(section)
            continue
        if re.search(r"(?m)^Status:\s*superseded\s*$", section, re.I):
            existing = re.search(r"(?m)^Superseded-By:\s*(\S+)", section)
            suffix = f" by {existing.group(1)}" if existing else ""
            raise ValueError(f"{old_id} is already superseded{suffix}.")
        if not re.search(r"(?m)^Status:\s*active\s*$", section, re.I):
            raise ValueError(f"{old_id} is not an active entry.")
        section = re.sub(r"(?m)^Status:\s*active\s*$", "Status: superseded", section, count=1)
        status_line = re.search(r"(?m)^Status:\s*superseded\s*$", section)
        assert status_line is not None
        insert = status_line.end()
        section = section[:insert] + f"\nSuperseded-By: {new_id}" + section[insert:]
        updated.append(section)
        changed = True
    if not changed:
        raise ValueError(f"Entry ID not found: {old_id}")
    parts = [preamble, *updated] if preamble else updated
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"
