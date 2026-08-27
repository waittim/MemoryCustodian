"""Stable Subject identity, normalization, parsing, and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
import re
import unicodedata
import uuid

from .entries import validate_evidence
from .markdown import canonical_h2_parts, render_canonical_h2, visible_lines
from .protocol import parse_markdown_units, read_managed_text


SUBJECT_ID_RE = re.compile(r"\bMC-SUBJ-(\d{8})-([0-9a-f]{8})\b", re.I)
SUBJECT_HEADING_ID_RE = re.compile(r"MC-SUBJ-\d{8}-[0-9a-f]{8}", re.I)
SUBJECT_KINDS = {
    "dependency",
    "repo-path",
    "area",
    "api",
    "service",
    "feature",
    "concept",
}
FACETS = {
    "adoption-policy",
    "version-policy",
    "architecture",
    "behavior",
    "compatibility",
    "security",
    "performance",
    "data-model",
    "interface",
    "workflow",
    "lifecycle",
}
SUBJECT_REQUIRED_TYPES = {"decision", "constraint", "tombstone", "do-not-use", "area"}
# Protocol 0.6 deliberately permits the complete canonical Facet vocabulary for
# every managed type. Keeping the matrix explicit makes admission deterministic
# and leaves later protocol versions a migration point for narrower combinations.
TYPE_FACETS = {
    "decision": FACETS,
    "constraint": FACETS,
    "tombstone": FACETS,
    "do-not-use": FACETS,
    "area": FACETS,
    "preference": FACETS,
    "rule": FACETS,
    "profile": FACETS,
}
_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z-]*):(?:\s*(.*))?$")
_SUBJECT_FIELDS = frozenset({
    "Status", "Kind", "Canonical-Ref", "Aliases", "Evidence",
    "Merged-Into", "Merged-From",
})
_SUBJECT_LIST_FIELDS = frozenset({"Aliases", "Evidence", "Merged-From"})
_PYPI_RUN_RE = re.compile(r"[-_.]+")
_SIMPLE_REF_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_NPM_REF_RE = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class Subject:
    subject_id: str
    title: str
    status: str
    kind: str
    canonical_ref: str | None
    aliases: tuple[str, ...]
    evidence: tuple[str, ...]
    text: str
    path: Path
    merged_into: str | None = None
    merged_from: tuple[str, ...] = ()
    field_counts: dict[str, int] = field(default_factory=dict)
    start_line: int = -1
    end_line: int = -1


class SubjectRegistryIssue(str):
    """A registry validation message with optional conflict finding metadata.

    The public validation helpers historically returned strings.  Keeping
    issues as ``str`` subclasses preserves that API for writers and previews,
    while allowing conflict analysis to consume a stable code assigned at the
    point where the invariant is detected instead of parsing message text.
    """

    conflict_code: str | None

    def __new__(
        cls,
        message: str,
        *,
        conflict_code: str | None = None,
    ) -> "SubjectRegistryIssue":
        instance = super().__new__(cls, message)
        instance.conflict_code = conflict_code
        return instance


def normalize_alias(value: str) -> str:
    """Normalize exact alias ownership without fuzzy or semantic matching."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.casefold().split())


def _normalize_repo_path(value: str) -> str:
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:", raw)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Invalid repo-path canonical reference: {value!r}")
    return path.as_posix()


def normalize_canonical_ref(value: str) -> str:
    raw = unicodedata.normalize("NFKC", value.strip())
    if raw.startswith("dependency:pypi:"):
        name = _PYPI_RUN_RE.sub("-", raw.removeprefix("dependency:pypi:").casefold())
        if not name or not _SIMPLE_REF_RE.fullmatch(name):
            raise ValueError(f"Invalid PyPI canonical reference: {value!r}")
        return f"dependency:pypi:{name}"
    if raw.startswith("dependency:npm:"):
        name = raw.removeprefix("dependency:npm:").casefold()
        if not _NPM_REF_RE.fullmatch(name):
            raise ValueError(f"Invalid npm canonical reference: {value!r}")
        return f"dependency:npm:{name}"
    if raw.startswith("repo-path:"):
        return f"repo-path:{_normalize_repo_path(raw.removeprefix('repo-path:'))}"
    for prefix in ("area:", "api:", "service:", "feature:"):
        if raw.startswith(prefix):
            identifier = raw.removeprefix(prefix).casefold()
            if not _SIMPLE_REF_RE.fullmatch(identifier):
                raise ValueError(f"Invalid {prefix[:-1]} canonical reference: {value!r}")
            return prefix + identifier
    raise ValueError(f"Unsupported Canonical-Ref: {value!r}")


def validate_subject_kind(kind: str) -> str:
    normalized = kind.strip().casefold()
    if normalized not in SUBJECT_KINDS:
        raise ValueError(
            f"Invalid Subject Kind {kind!r}; expected one of: {', '.join(sorted(SUBJECT_KINDS))}"
        )
    return normalized


def validate_facet(kind: str, facet: str) -> str:
    normalized_kind = "area" if kind == "area" else kind
    normalized = facet.strip().casefold()
    allowed = TYPE_FACETS.get(normalized_kind)
    if allowed is None or normalized not in allowed:
        expected = ", ".join(sorted(allowed or FACETS))
        raise ValueError(f"Facet {facet!r} is not valid for {kind}; expected one of: {expected}")
    return normalized


def subject_required(kind: str, *, candidate: bool = False, area: str | None = None) -> bool:
    if candidate:
        return False
    return kind in SUBJECT_REQUIRED_TYPES or (area is not None and kind in {"decision", "constraint", "tombstone", "do-not-use"})


def generate_subject_id(existing_ids: set[str] | None = None, *, day: date | None = None) -> str:
    used = {item.casefold() for item in (existing_ids or set())}
    stamp = (day or date.today()).strftime("%Y%m%d")
    while True:
        value = f"MC-SUBJ-{stamp}-{uuid.uuid4().hex[:8]}"
        if value.casefold() not in used:
            return value


def parse_subject_registry(path: Path, text: str) -> tuple[list[Subject], list[str]]:
    subjects: list[Subject] = []
    issues: list[str] = []
    for unit in parse_markdown_units(text).units:
        if unit.kind != "h2":
            continue
        section = unit.text
        first_line = section.splitlines()[0]
        heading = canonical_h2_parts(first_line, SUBJECT_HEADING_ID_RE)
        if heading is None:
            issues.append(
                f"{path.name}: malformed Subject heading {first_line!r}; "
                "expected `## <SUBJECT_ID> — <title>`"
            )
            continue
        fields: dict[str, str] = {}
        field_counts: dict[str, int] = {}
        aliases: list[str] = []
        evidence: list[str] = []
        merged_from: list[str] = []
        list_field: str | None = None
        for visible in visible_lines(section):
            if visible.indented_code:
                continue
            if visible.index == 0:
                continue
            line = visible.text
            field = _FIELD_RE.match(line)
            if field:
                key, field_value = field.group(1), (field.group(2) or "").strip()
                if key not in _SUBJECT_FIELDS:
                    issues.append(f"{path.name}: {heading[0]} has unknown field {key}")
                    list_field = None
                    continue
                fields[key] = field_value
                field_counts[key] = field_counts.get(key, 0) + 1
                if key in _SUBJECT_LIST_FIELDS:
                    if field_value:
                        issues.append(
                            f"{path.name}: {heading[0]} {key} block heading must not contain a value"
                        )
                    list_field = key
                else:
                    if not field_value:
                        issues.append(f"{path.name}: {heading[0]} {key} must not be empty")
                    list_field = None
                continue
            if line.startswith("- ") and list_field == "Aliases":
                value = line[2:].strip()
                if not value:
                    issues.append(f"{path.name}: {heading[0]} Aliases contains an empty item")
                aliases.append(value)
            elif line.startswith("- ") and list_field == "Evidence":
                value = line[2:].strip()
                if not value:
                    issues.append(f"{path.name}: {heading[0]} Evidence contains an empty item")
                evidence.append(value)
            elif line.startswith("- ") and list_field == "Merged-From":
                value = line[2:].strip()
                if not value:
                    issues.append(f"{path.name}: {heading[0]} Merged-From contains an empty item")
                merged_from.append(value)
            elif line.strip():
                issues.append(
                    f"{path.name}: {heading[0]} has unexpected line {line!r}"
                )
                list_field = None
        subjects.append(
            Subject(
                heading[0],
                heading[1],
                fields.get("Status", ""),
                fields.get("Kind", ""),
                fields.get("Canonical-Ref") or None,
                tuple(aliases),
                tuple(evidence),
                section,
                path,
                fields.get("Merged-Into") or None,
                tuple(merged_from),
                field_counts,
                unit.start_line,
                unit.end_line,
            )
        )
    return subjects, issues


def parse_subjects(path: Path, text: str) -> list[Subject]:
    return parse_subject_registry(path, text)[0]


def load_subjects(memory_dir: Path) -> list[Subject]:
    path = memory_dir / "subjects.md"
    if not path.exists():
        return []
    return parse_subjects(path, read_managed_text(memory_dir, path))


def render_subject(
    subject_id: str,
    title: str,
    kind: str,
    canonical_ref: str | None,
    aliases: tuple[str, ...],
    evidence: tuple[str, ...],
    *,
    status: str = "active",
    merged_into: str | None = None,
    merged_from: tuple[str, ...] = (),
) -> str:
    normalized_title = " ".join(title.split())
    normalized_aliases = tuple(
        dict.fromkeys(" ".join(item.split()) for item in aliases if item.split())
    )
    lines = [
        render_canonical_h2(subject_id, normalized_title),
        "",
        f"Status: {status}",
        f"Kind: {kind}",
    ]
    if canonical_ref:
        lines.append(f"Canonical-Ref: {canonical_ref}")
    if merged_into:
        lines.append(f"Merged-Into: {merged_into}")
    lines.extend(["Evidence:", *(f"- {item}" for item in evidence), "", "Aliases:"])
    lines.extend(f"- {item}" for item in normalized_aliases)
    if merged_from:
        lines.extend(["", "Merged-From:"])
        lines.extend(f"- {item}" for item in merged_from)
    rendered = "\n".join(lines)
    parsed = parse_subjects(Path("__rendered_subject__.md"), rendered)
    if (
        len(parsed) != 1
        or parsed[0].subject_id.casefold() != subject_id.casefold()
        or parsed[0].status != status
        or parsed[0].merged_into != merged_into
        or parsed[0].title != normalized_title
        or parsed[0].aliases != normalized_aliases
        or parsed[0].merged_from != merged_from
    ):
        raise ValueError("Rendered Subject did not round-trip safely.")
    return rendered


def subject_indexes(subjects: list[Subject]) -> tuple[dict[str, Subject], dict[str, Subject], dict[str, Subject]]:
    by_id: dict[str, Subject] = {}
    by_alias: dict[str, Subject] = {}
    by_ref: dict[str, Subject] = {}
    for subject in subjects:
        if subject.status != "active":
            continue
        by_id[subject.subject_id.casefold()] = subject
        for alias in (subject.title, *subject.aliases):
            normalized = normalize_alias(alias)
            if normalized:
                by_alias[normalized] = subject
        if subject.canonical_ref:
            by_ref[normalize_canonical_ref(subject.canonical_ref)] = subject
    return by_id, by_alias, by_ref


def subject_registry_issues(
    subjects: list[Subject],
    parse_issues: list[str] | tuple[str, ...],
    project_root: Path,
) -> list[str]:
    """Validate already parsed registry state, including Git revision content."""

    issues = list(parse_issues)
    ids: dict[str, str] = {}
    aliases: dict[str, str] = {}
    refs: dict[str, str] = {}
    for subject in subjects:
        key = subject.subject_id.casefold()
        if key in ids:
            issues.append(f"subjects.md: duplicate Subject ID {subject.subject_id}")
        ids[key] = subject.subject_id
        for name, count in sorted(subject.field_counts.items()):
            if count > 1:
                issues.append(
                    f"subjects.md: {subject.subject_id} has duplicate {name} fields"
                )
        for name in ("Status", "Kind", "Evidence", "Aliases"):
            count = subject.field_counts.get(name, 0)
            if count != 1:
                issues.append(
                    f"subjects.md: {subject.subject_id} must declare exactly one {name} field "
                    f"(found {count})"
                )
        if subject.status not in {"active", "merged"}:
            issues.append(f"subjects.md: {subject.subject_id} has invalid Status {subject.status!r}")
        if subject.status == "merged" and not subject.merged_into:
            issues.append(f"subjects.md: {subject.subject_id} merged Subject lacks Merged-Into")
        if subject.status == "active" and subject.merged_into:
            issues.append(f"subjects.md: {subject.subject_id} active Subject cannot declare Merged-Into")
        if subject.status == "merged" and subject.merged_from:
            issues.append(f"subjects.md: {subject.subject_id} merged Subject cannot declare Merged-From")
        if len({item.casefold() for item in subject.merged_from}) != len(subject.merged_from):
            issues.append(f"subjects.md: {subject.subject_id} has duplicate Merged-From values")
        try:
            validate_subject_kind(subject.kind)
        except ValueError as exc:
            issues.append(f"subjects.md: {subject.subject_id}: {exc}")
        try:
            validate_evidence(subject.evidence, project_root, allow_missing=True)
        except ValueError as exc:
            issues.append(f"subjects.md: {subject.subject_id}: {exc}")
        if subject.status != "active":
            continue
        for alias in (subject.title, *subject.aliases):
            normalized = normalize_alias(alias)
            owner = aliases.get(normalized)
            if owner and owner.casefold() != subject.subject_id.casefold():
                issues.append(SubjectRegistryIssue(
                    f"subjects.md: normalized alias {alias!r} is owned by both {owner} and {subject.subject_id}",
                    conflict_code="MC-CONFLICT-004",
                ))
            aliases[normalized] = subject.subject_id
        if subject.canonical_ref:
            try:
                normalized_ref = normalize_canonical_ref(subject.canonical_ref)
            except ValueError as exc:
                issues.append(f"subjects.md: {subject.subject_id}: {exc}")
                continue
            owner = refs.get(normalized_ref)
            if owner and owner.casefold() != subject.subject_id.casefold():
                issues.append(SubjectRegistryIssue(
                    f"subjects.md: Canonical-Ref {normalized_ref!r} is owned by both {owner} and {subject.subject_id}",
                    conflict_code="MC-CONFLICT-003",
                ))
            refs[normalized_ref] = subject.subject_id
    by_id = {item.subject_id.casefold(): item for item in subjects}
    for subject in subjects:
        if subject.status == "merged":
            if not subject.merged_into:
                continue
            target = by_id.get(subject.merged_into.casefold())
            if target is None or target.status != "active" or target.subject_id.casefold() == subject.subject_id.casefold():
                issues.append(
                    f"subjects.md: {subject.subject_id} Merged-Into must reference a different active Subject"
                )
        elif subject.status == "active" and subject.merged_from:
            for source_id in subject.merged_from:
                source = by_id.get(source_id.casefold())
                if source is None or source.status != "merged" or (source.merged_into or "").casefold() != subject.subject_id.casefold():
                    issues.append(
                        f"subjects.md: {subject.subject_id} Merged-From references a non-reciprocal source {source_id}"
                    )
    return issues


def validate_subject_registry(memory_dir: Path, project_root: Path) -> list[str]:
    path = memory_dir / "subjects.md"
    if not path.exists():
        return ["subjects.md: missing managed Subject registry"]
    text = read_managed_text(memory_dir, path)
    subjects, parse_issues = parse_subject_registry(path, text)
    return subject_registry_issues(subjects, parse_issues, project_root)
