"""Protocol 0.7 entry identity, evidence, parsing, and rendering."""

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
ENTRY_HEADING_ID_RE = re.compile(
    r"MC-(?:DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-\d{8}-[0-9a-f]{8}", re.I
)
ACTIVE_EVIDENCE_RE = re.compile(
    r"^(?:user-confirmed|(?:repo|doc|test):[^@\s]+(?:@[A-Za-z0-9._-]+)?|issue:#\d+|pr:#\d+)$"
)
CANDIDATE_ONLY_EVIDENCE = {"agent-observed", "conversation-unconfirmed"}
INTERNAL_EVIDENCE = {"legacy-unverified"}
VALID_SCOPES_RE = re.compile(r"^(?:project|area:[A-Za-z0-9][A-Za-z0-9._-]*|local-user|local-machine)$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z-]*):(?:\s*(.*))?$")
# This visible entity is a private, line-local writer escape.  Indenting a
# protocol-shaped body line cannot be made unambiguous: every indentation width
# at or above four spaces is valid Markdown indented code.  The marker keeps
# the rendered line at column zero while giving the parser an explicit
# representation to decode, without putting hidden format characters in the
# source.  A leading marker in user content is doubled so the encoding remains
# reversible for renderer input as well.
BODY_SAFETY_SENTINEL = "&#8283;"


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


class EntryUnitIssue(str):
    """An entry-unit diagnostic with safety metadata for conflict consumers."""

    conflict_relevant: bool

    def __new__(
        cls,
        message: str,
        *,
        conflict_relevant: bool = True,
    ) -> "EntryUnitIssue":
        instance = super().__new__(cls, message)
        instance.conflict_relevant = conflict_relevant
        return instance


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
ENTRY_FIELDS = frozenset({
    "Status",
    "Scope",
    "Subject",
    "Facet",
    "Evidence",
    "Supersedes",
    "Superseded-By",
    "Promoted-From",
    "Promoted-To",
    "Exception-To",
    "Candidate-Type",
    "Provisional-Subject",
    "Provisional-Facet",
    "Promotion-Requirement",
    "Reason",
    *TYPED_BODY_FIELDS,
})
ENTRY_SCALAR_FIELDS = ENTRY_FIELDS - {
    "Evidence",
    "Reason",
    "Promotion-Requirement",
    *TYPED_BODY_FIELDS,
}
STRUCTURAL_ENTRY_CODES = frozenset({"DEC", "CON", "DNU", "AREA"})
VALID_ENTRY_STATUSES = frozenset({"active", "candidate", "superseded", "promoted"})


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
    from .markdown import canonical_h2_parts
    from .protocol import parse_markdown_units

    found: list[str] = []
    for unit in parse_markdown_units(text).units:
        if unit.kind != "h2" or unit.heading is None:
            continue
        parsed = canonical_h2_parts(unit.text.splitlines()[0], ENTRY_HEADING_ID_RE)
        if parsed:
            found.append(parsed[0])
    return found


def entry_unit_issues(text: str, relative_path: str) -> list[str]:
    """Return canonical-heading and ambiguous formal-unit findings."""

    from .markdown import canonical_h2_parts
    from .protocol import parse_markdown_units

    issues: list[str] = []
    for unit in parse_markdown_units(text).units:
        if unit.kind == "h2" and unit.heading and ENTRY_ID_RE.search(unit.heading):
            if canonical_h2_parts(unit.text.splitlines()[0], ENTRY_HEADING_ID_RE) is None:
                issues.append(
                    f"{relative_path}: malformed Entry heading {unit.text.splitlines()[0]!r}; "
                    "expected `## <ENTRY_ID> — <title>`"
                )
        elif unit.kind == "ambiguous-bullet":
            issues.append(EntryUnitIssue(
                f"{relative_path}: ambiguous column-zero bullet follows a formal Entry; "
                "indent body bullets or move legacy memory under an explicit heading",
                conflict_relevant=False,
            ))
    return issues


def memory_entry_ids(memory_dir: Path) -> set[str]:
    from .protocol import canonical_memory_files, read_managed_text

    found: set[str] = set()
    if not memory_dir.exists():
        return found
    # README files are documentation, even when they happen to contain an
    # Entry-looking example.  Inventory only manifest-authorized canonical
    # storage (including archive for ID uniqueness); this also keeps examples
    # from reserving IDs or becoming relation operands.
    for path in canonical_memory_files(memory_dir, include_archive=True):
        for value in heading_entry_ids(read_managed_text(memory_dir, path)):
            found.add(value)
    return found


def memory_entry_id_counts(memory_dir: Path) -> dict[str, int]:
    """Count canonical heading IDs across all shared managed-memory storage."""

    from .protocol import canonical_memory_files, read_managed_text

    counts: dict[str, int] = {}
    if not memory_dir.exists():
        return counts
    for path in canonical_memory_files(memory_dir, include_archive=True):
        for value in heading_entry_ids(read_managed_text(memory_dir, path)):
            key = value.casefold()
            counts[key] = counts.get(key, 0) + 1
    return counts


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
        raise ValueError("Protocol 0.7 active memory requires at least one --evidence value.")
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


def line_safe_markdown_body(value: str) -> str:
    """Serialize body text without creating column-zero protocol structure."""

    safe: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in value.splitlines():
        if fence_character is not None:
            safe.append(line)
            if re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                line,
            ):
                fence_character = None
                fence_length = 0
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening:
            marker = opening.group(1)
            if marker[0] == "`" and "`" in opening.group(2):
                raise ValueError("Backtick fence info strings must not contain backticks")
            fence_character = marker[0]
            fence_length = len(marker)
            safe.append(line)
            continue
        if line.startswith(BODY_SAFETY_SENTINEL):
            # Escape the sentinel itself before the parser's protocol-shape
            # check so literal user content cannot be consumed as encoding.
            safe.append(BODY_SAFETY_SENTINEL + line)
        elif FIELD_RE.match(line) or line.startswith(("## ", "- ", "* ", "+ ")):
            safe.append(BODY_SAFETY_SENTINEL + line)
        else:
            safe.append(line)
    if fence_character is not None:
        raise ValueError("Body contains an unclosed fenced code block.")
    return "\n".join(safe)


def render_markdown_bullet(value: str) -> str:
    """Render one top-level bullet while keeping every later line inside it."""

    lines = value.splitlines()
    if not any(line.strip() for line in lines):
        raise ValueError("Memory body must not be empty.")
    return "- " + lines[0] + "".join(f"\n  {line}" for line in lines[1:])


def _normalized_body(value: str) -> str:
    """Normalize line endings without changing body content.

    Field bodies are parsed from Markdown source ranges.  Blank lines,
    indentation, and trailing spaces are data, not formatting that the
    protocol may silently discard.  The parser removes separator blank lines
    around a field; apply the same boundary rule to bodies supplied to a
    renderer or validator so the two paths compare the same representation.
    """

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    # split("\n") intentionally keeps interior and terminal empty lines.  A
    # terminal empty line is the field separator in a structured Entry, while
    # interior empty lines are paragraph content and must survive.
    lines = normalized.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _decoded_body_line(raw_line: str, visible) -> str | None:
    """Decode an explicit writer escape or preserve a Markdown code line.

    Protocol-shaped body lines are prefixed with ``BODY_SAFETY_SENTINEL`` by
    ``line_safe_markdown_body``.  Unlike an indentation heuristic, this
    representation is distinguishable from every native four-, five-, or
    eight-space indented-code line.  A doubled sentinel is the escaped form
    for literal user content that starts with the sentinel.  Fenced lines are
    not passed to this helper and therefore remain opaque source content.

    ``None`` means the line is not an encoded body line and should continue
    through the normal field parser.  An ordinary indented line is returned
    unchanged so callers retain its exact source whitespace.
    """

    if raw_line.startswith(BODY_SAFETY_SENTINEL):
        candidate = raw_line[len(BODY_SAFETY_SENTINEL):]
        if candidate.startswith(BODY_SAFETY_SENTINEL):
            return candidate
        if FIELD_RE.match(candidate) or candidate.startswith(("## ", "- ", "* ", "+ ")):
            return candidate
        # A non-protocol line with a lone sentinel is ordinary user text, not
        # a writer escape.  Leave it for the normal non-field body path.
        return None
    if visible.indented_code:
        return raw_line
    return None


def _validate_rendered_entry(
    text: str,
    entry_id: str,
    body_field: str,
    body: str,
    extra_body_field: str | None = None,
    extra_body: str | None = None,
) -> None:
    if not _normalized_body(body):
        raise ValueError(f"Rendered Entry {body_field} body must not be empty.")
    parsed = parse_structured_entries(Path("__rendered_entry__.md"), text)
    if len(parsed) != 1 or parsed[0].entry_id.casefold() != entry_id.casefold():
        raise ValueError("Rendered Entry did not round-trip as exactly one structured Entry.")
    entry = parsed[0]
    if (
        entry.field_counts.get(body_field) != 1
        or entry.field_bodies.get(body_field, "") != _normalized_body(body)
    ):
        raise ValueError(f"Rendered Entry {body_field} body did not round-trip safely.")
    if extra_body_field is not None and (
        entry.field_counts.get(extra_body_field) != 1
        or entry.field_bodies.get(extra_body_field, "") != _normalized_body(extra_body or "")
    ):
        raise ValueError(f"Rendered Entry {extra_body_field} body did not round-trip safely.")


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
    promoted_from: str | None = None,
) -> str:
    from .markdown import render_canonical_h2

    normalized_title = " ".join(title.split())
    if not normalized_title:
        raise ValueError("Rendered Entry title must not be empty.")
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
    heading_title = (
        f"Tombstone: {normalized_title}"
        if kind in {"tombstone", "do-not-use"}
        else normalized_title
    )
    lines = [
        render_canonical_h2(entry_id, heading_title),
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
    if promoted_from:
        lines.append(f"Promoted-From: {promoted_from}")
    body_field = labels[kind]
    lines.extend(["", f"{body_field}:", line_safe_markdown_body(message)])
    if reason:
        lines.extend(["", "Reason:", line_safe_markdown_body(reason)])
    rendered = "\n".join(lines)
    _validate_rendered_entry(
        rendered, entry_id, body_field, message,
        "Reason" if reason else None, reason,
    )
    return rendered


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
    from .markdown import render_canonical_h2

    normalized_title = " ".join(title.split())
    if not normalized_title:
        raise ValueError("Rendered Entry title must not be empty.")
    promotion_requirement = (
        note.strip()
        if note is not None and note.strip()
        else "Confirm with the user or an authoritative project source."
    )
    lines = [
        render_canonical_h2(entry_id, normalized_title),
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
        line_safe_markdown_body(message),
        "",
        "Promotion-Requirement:",
        line_safe_markdown_body(promotion_requirement),
    ])
    rendered = "\n".join(lines)
    _validate_rendered_entry(
        rendered, entry_id, "Statement", message,
        "Promotion-Requirement",
        promotion_requirement,
    )
    return rendered


def parse_structured_entries(path: Path, text: str) -> list[StructuredEntry]:
    from .protocol import parse_markdown_units
    from .markdown import canonical_h2_parts, visible_lines

    sections = [
        unit.text
        for unit in parse_markdown_units(text).units
        if unit.kind == "h2"
    ]
    parsed: list[StructuredEntry] = []
    for section in sections:
        lines = section.splitlines()
        heading = canonical_h2_parts(lines[0], ENTRY_HEADING_ID_RE)
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

        visible_by_index = {
            line.index: line for line in visible_lines(section)
        }
        for line_index, raw_line in enumerate(lines):
            if line_index == 0:
                continue
            visible = visible_by_index.get(line_index)
            if visible is None:
                if current_field is not None:
                    current_body.append(raw_line)
                continue
            if current_field is not None:
                decoded = _decoded_body_line(raw_line, visible)
                if decoded is not None:
                    current_body.append(decoded)
                    continue
            if visible.indented_code:
                continue
            line = visible.text
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
            elif current_field is not None:
                # Preserve paragraph separators, trailing spaces, and
                # continuation indentation.  Only blank lines at the start
                # or end of an occurrence are removed by _normalized_body;
                # those are field separators rather than body content.
                current_body.append(raw_line)
        flush_field()
        field_bodies = {
            key: _normalized_body(
                "\n".join(
                    line
                    for occurrence in occurrences
                    for line in occurrence
                )
            )
            for key, occurrences in occurrence_bodies.items()
        }
        title = heading[1]
        parsed.append(
            StructuredEntry(
                heading[0],
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
    *,
    require_active_identity: bool = False,
) -> list[str]:
    """Validate the declared Protocol 0.7 structure of one formal entry."""

    issues: list[str] = []
    prefix = f"{relative_path}: {entry.entry_id}"
    for name in sorted(set(entry.field_counts) - ENTRY_FIELDS):
        issues.append(f"{prefix} has unknown field {name}")

    for name in sorted(set(entry.field_counts) & ENTRY_SCALAR_FIELDS):
        if not entry.fields.get(name, "").strip():
            issues.append(f"{prefix} {name} must not be empty")
        if (
            entry.field_counts.get(name) == 1
            and entry.field_bodies.get(name, "")
            != _normalized_body(entry.fields.get(name, ""))
        ):
            issues.append(
                f"{prefix} scalar field {name} has an unexpected visible continuation line"
            )

    for name in ("Status", "Scope", "Evidence"):
        count = entry.field_counts.get(name, 0)
        if count != 1:
            issues.append(f"{prefix} must declare exactly one {name} field (found {count})")
    if entry.field_counts.get("Evidence") == 1 and not entry.evidence:
        issues.append(f"{prefix} Evidence must contain at least one non-empty item")
    elif entry.field_counts.get("Evidence") == 1 and any(
        not value.strip() for value in entry.evidence
    ):
        issues.append(f"{prefix} Evidence must not contain empty items")

    if entry.status not in VALID_ENTRY_STATUSES:
        issues.append(f"{prefix} has invalid Status {entry.status!r}")
    if VALID_SCOPES_RE.fullmatch(entry.scope) is None:
        issues.append(f"{prefix} has invalid Scope {entry.scope!r}")

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
    if entry.status == "superseded" and not entry.fields.get("Superseded-By", "").strip():
        issues.append(f"{prefix} superseded entry has no Superseded-By")
    if entry.status == "promoted" and not entry.fields.get("Promoted-To", "").strip():
        issues.append(f"{prefix} promoted entry has no Promoted-To")

    if require_active_identity and entry.status == "active":
        code = entry.entry_id.split("-", 2)[1].upper()
        if code in STRUCTURAL_ENTRY_CODES and not relative_path.startswith(("rules/", "profiles/")):
            for name in ("Subject", "Facet"):
                if entry.field_counts.get(name) != 1 or not entry.fields.get(name, "").strip():
                    issues.append(
                        f"{prefix} active structural Entry must declare a non-empty {name}"
                    )

    if entry.status in {"candidate", "promoted"}:
        provisional_subject = entry.fields.get("Provisional-Subject", "").strip()
        provisional_facet = entry.fields.get("Provisional-Facet", "").strip()
        if bool(provisional_subject) != bool(provisional_facet):
            issues.append(
                f"{prefix} must declare Provisional-Subject and Provisional-Facet together"
            )
        candidate_type_count = entry.field_counts.get("Candidate-Type", 0)
        if candidate_type_count != 1:
            issues.append(
                f"{prefix} must declare exactly one Candidate-Type field "
                f"(found {candidate_type_count})"
            )
        requirement_count = entry.field_counts.get("Promotion-Requirement", 0)
        if requirement_count != 1:
            issues.append(
                f"{prefix} must declare exactly one Promotion-Requirement field "
                f"(found {requirement_count})"
            )
        elif not entry.field_bodies.get("Promotion-Requirement", "").strip():
            issues.append(f"{prefix} has an empty Promotion-Requirement body")
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
        if entry.status not in {"candidate", "promoted"}:
            issues.append(
                f"{prefix} has Status {entry.status!r}; inbox entries must be candidate or promoted"
            )
        return issues

    if code == "INBOX":
        issues.append(f"{prefix} must be stored in inbox.md")
        return issues
    if entry.status in {"candidate", "promoted"}:
        issues.append(f"{prefix} {entry.status} Entry must be stored in inbox.md")
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


def parse_entry_inventory(
    path: Path,
    text: str,
    relative_path: str,
    project_root: Path,
    *,
    require_active_identity: bool = False,
) -> tuple[tuple[StructuredEntry, ...], tuple[str, ...]]:
    """Parse entries together with the complete integrity issues for a file.

    Readers that make safety decisions (conflict and merge review in
    particular) must not silently discard malformed formal units.  The normal
    check command already reports these components independently; this helper
    gives read-only decision paths the same evidence without introducing a
    second schema implementation.
    """

    issues: list[str] = []
    try:
        issues.extend(entry_unit_issues(text, relative_path))
        parsed = tuple(parse_structured_entries(path, text))
    except (TypeError, ValueError) as exc:
        return (), (f"{relative_path}: Markdown entry parsing failed: {exc}",)
    for entry in parsed:
        issues.extend(
            structured_entry_schema_issues(
                entry,
                relative_path,
                require_active_identity=require_active_identity,
            )
        )
        issues.extend(structured_entry_storage_issues(entry, relative_path))
        if entry.evidence:
            try:
                validate_evidence(
                    entry.evidence,
                    project_root,
                    candidate=entry.status in {"candidate", "promoted"},
                    allow_missing=True,
                    allow_internal=entry.status not in {"candidate", "promoted"},
                )
            except ValueError as exc:
                # Keep diagnostics deterministic and avoid echoing arbitrary
                # evidence payloads (which may contain sensitive text).
                issues.append(
                    f"{relative_path}: {entry.entry_id} has invalid Evidence schema or unsafe source path"
                )
    return parsed, tuple(dict.fromkeys(issues))


def structured_relation_issues(
    entries: list[StructuredEntry],
    *,
    merged_subject_ids: set[str] | None = None,
) -> list[str]:
    """Validate reciprocal lifecycle relations and preserved structural identity."""

    by_id: dict[str, list[StructuredEntry]] = {}
    merged_subjects = {value.casefold() for value in (merged_subject_ids or set())}
    for entry in entries:
        by_id.setdefault(entry.entry_id.casefold(), []).append(entry)
    issues: set[str] = set()

    def unique(entry_id: str) -> StructuredEntry | None:
        matches = by_id.get(entry_id.casefold(), [])
        return matches[0] if len(matches) == 1 else None

    def identity(entry: StructuredEntry) -> tuple[str, str, str]:
        return (
            entry.scope.casefold(),
            entry.fields.get("Subject", "").casefold(),
            entry.fields.get("Facet", "").casefold(),
        )

    for entry in entries:
        for relation in (
            "Supersedes",
            "Superseded-By",
            "Promoted-From",
            "Promoted-To",
            "Exception-To",
        ):
            target_id = entry.fields.get(relation, "")
            if not target_id:
                continue
            matches = by_id.get(target_id.casefold(), [])
            if not matches:
                issues.add(f"{entry.entry_id} {relation} references missing entry {target_id}")
            elif len(matches) != 1:
                issues.add(
                    f"{entry.entry_id} {relation} target {target_id} resolves to "
                    f"{len(matches)} entries; relation targets must be unique"
                )

        exception_target_id = entry.fields.get("Exception-To", "")
        if exception_target_id:
            target_matches = by_id.get(exception_target_id.casefold(), [])
            if (
                entry.status != "active"
                or not entry.scope.casefold().startswith("area:")
                or len(target_matches) != 1
                or target_matches[0].status != "active"
                or target_matches[0].scope.casefold() != "project"
                or bool(target_matches[0].fields.get("Exception-To"))
                or (
                    entry.fields.get("Subject", "").casefold()
                    != target_matches[0].fields.get("Subject", "").casefold()
                )
                or (
                    entry.fields.get("Facet", "").casefold()
                    != target_matches[0].fields.get("Facet", "").casefold()
                )
            ):
                issues.add(
                    f"{entry.entry_id} Exception-To relation is invalid; it must point from an active area owner to a matching project owner"
                )

        previous_id = entry.fields.get("Supersedes", "")
        previous = unique(previous_id) if previous_id else None
        if previous is not None:
            if entry.status not in {"active", "superseded"} or previous.status != "superseded":
                issues.add(
                    f"{entry.entry_id} Supersedes requires a current/historical replacement and superseded source"
                )
            if previous.fields.get("Superseded-By", "").casefold() != entry.entry_id.casefold():
                issues.add(f"{entry.entry_id} Supersedes relation is not reciprocal")
            if identity(entry) != identity(previous):
                issues.add(
                    f"{entry.entry_id} Supersedes must preserve Scope+Subject+Facet identity"
                )

        replacement_id = entry.fields.get("Superseded-By", "")
        replacement = unique(replacement_id) if replacement_id else None
        if replacement is not None:
            if entry.status != "superseded" or replacement.status not in {"active", "superseded"}:
                issues.add(
                    f"{entry.entry_id} Superseded-By requires a superseded source and current/historical replacement"
                )
            if replacement.fields.get("Supersedes", "").casefold() != entry.entry_id.casefold():
                issues.add(f"{entry.entry_id} Superseded-By relation is not reciprocal")
            if identity(entry) != identity(replacement):
                issues.add(
                    f"{entry.entry_id} Superseded-By must preserve Scope+Subject+Facet identity"
                )

        source_id = entry.fields.get("Promoted-From", "")
        source = unique(source_id) if source_id else None
        if source is not None:
            expected_codes = {
                "decision": "DEC",
                "constraint": "CON",
                "preference": "PREF",
                "tombstone": "DNU",
                "do-not-use": "DNU",
            }
            target_code = entry.entry_id.split("-", 2)[1].upper()
            candidate_type = source.fields.get("Candidate-Type", "").casefold()
            expected_code = expected_codes.get(candidate_type)
            if candidate_type == "decision" and source.scope.casefold().startswith("area:"):
                expected_code = "AREA"
            if entry.status != "active" or source.status != "promoted":
                issues.add(
                    f"{entry.entry_id} Promoted-From requires an active target and promoted candidate"
                )
            if source.fields.get("Promoted-To", "").casefold() != entry.entry_id.casefold():
                issues.add(f"{entry.entry_id} Promoted-From relation is not reciprocal")
            if expected_code != target_code:
                issues.add(
                    f"{entry.entry_id} type does not match source Candidate-Type {candidate_type!r}"
                )
            if entry.scope.casefold() != source.scope.casefold():
                issues.add(f"{entry.entry_id} promotion must preserve Scope")
            provisional = (
                source.fields.get("Provisional-Subject", "").casefold(),
                source.fields.get("Provisional-Facet", "").casefold(),
            )
            target_identity = (
                entry.fields.get("Subject", "").casefold(),
                entry.fields.get("Facet", "").casefold(),
            )
            if provisional != ("", "") and provisional != target_identity:
                issues.add(f"{entry.entry_id} promotion must preserve provisional Subject+Facet")

        target_id = entry.fields.get("Promoted-To", "")
        target = unique(target_id) if target_id else None
        if target is not None:
            if entry.status != "promoted" or target.status != "active":
                issues.add(
                    f"{entry.entry_id} Promoted-To requires a promoted candidate and active target"
                )
            if target.fields.get("Promoted-From", "").casefold() != entry.entry_id.casefold():
                issues.add(f"{entry.entry_id} Promoted-To relation is not reciprocal")

    successor: dict[str, str] = {}
    for entry in entries:
        if entry.status != "superseded":
            continue
        if unique(entry.entry_id) is None:
            continue
        replacement_id = entry.fields.get("Superseded-By", "")
        if not replacement_id:
            # A historical Entry whose Subject was merged is terminal by the
            # Subject lifecycle, not by an active Entry replacement.  Other
            # superseded entries still require an explicit successor.
            if entry.fields.get("Subject", "").casefold() not in merged_subjects:
                issues.add(
                    f"{entry.entry_id} supersession chain does not terminate at an active replacement"
                )
            continue
        if unique(replacement_id) is not None:
            successor[entry.entry_id.casefold()] = replacement_id.casefold()

    checked: set[str] = set()
    for start in sorted(successor):
        if start in checked:
            continue
        order: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in successor:
            if current in positions:
                cycle = order[positions[current]:]
                labels = [unique(value).entry_id for value in cycle]
                start_at = min(range(len(labels)), key=lambda index: labels[index].casefold())
                labels = labels[start_at:] + labels[:start_at]
                issues.add("supersession cycle detected: " + " -> ".join([*labels, labels[0]]))
                break
            if current in checked:
                break
            positions[current] = len(order)
            order.append(current)
            current = successor[current]
        terminal = unique(current)
        if current not in successor and terminal is not None and terminal.status != "active":
            issues.add(
                f"{unique(start).entry_id} supersession chain does not terminate at an active replacement"
            )
        checked.update(order)

    return sorted(issues)


def supersede_entry(
    text: str,
    old_id: str,
    new_id: str,
    *,
    relative_path: str = "__supersession__.md",
) -> str:
    from .markdown import visible_lines
    from .protocol import parse_markdown_units

    document = parse_markdown_units(text)
    source_lines = text.splitlines(keepends=True)
    changed = False
    for unit in document.units:
        if unit.kind != "h2":
            continue
        section = unit.text
        parsed = parse_structured_entries(Path(relative_path), section)
        if len(parsed) != 1 or parsed[0].entry_id.casefold() != old_id.casefold():
            continue
        entry = parsed[0]
        if entry.status == "superseded":
            existing = entry.fields.get("Superseded-By", "")
            suffix = f" by {existing}" if existing else ""
            raise ValueError(f"{old_id} is already superseded{suffix}.")
        if entry.status != "active" or entry.field_counts.get("Status") != 1:
            raise ValueError(f"{old_id} is not an active entry.")
        status_indices = [
            line.index
            for line in visible_lines(section)
            if re.fullmatch(r"Status:\s*active\s*", line.text, re.I)
        ]
        if len(status_indices) != 1:
            raise ValueError(f"{old_id} has no unique visible active Status field.")
        status_index = status_indices[0]
        lines = section.splitlines()
        lines[status_index:status_index + 1] = [
            "Status: superseded",
            f"Superseded-By: {new_id}",
        ]
        section = "\n".join(lines)
        resulting = parse_structured_entries(Path(relative_path), section)
        if len(resulting) != 1 or (
            structured_entry_schema_issues(resulting[0], relative_path)
            or (
                relative_path != "__supersession__.md"
                and structured_entry_storage_issues(resulting[0], relative_path)
            )
        ):
            raise ValueError(f"Supersession would make {old_id} structurally invalid.")
        absolute_status_index = unit.start_line + status_index
        if absolute_status_index >= len(source_lines):
            raise ValueError("Supersession source changed while building mutation.")
        original_line = source_lines[absolute_status_index]
        line_ending = (
            "\r\n" if original_line.endswith("\r\n")
            else "\n" if original_line.endswith("\n")
            else ""
        )
        source_lines[absolute_status_index] = (
            "Status: superseded" + line_ending
            + f"Superseded-By: {new_id}" + line_ending
        )
        changed = True
    if not changed:
        raise ValueError(f"Entry ID not found: {old_id}")
    return "".join(source_lines)
