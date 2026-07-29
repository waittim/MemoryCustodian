"""Stable Subject identity, normalization, parsing, and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
import re
import unicodedata
import uuid

from .entries import validate_evidence


SUBJECT_ID_RE = re.compile(r"\bMC-SUBJ-(\d{8})-([0-9a-f]{8})\b", re.I)
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


def parse_subjects(path: Path, text: str) -> list[Subject]:
    matches = list(re.finditer(r"(?m)^## (MC-SUBJ-\d{8}-[0-9a-f]{8})\s+—\s+(.+)$", text, re.I))
    subjects: list[Subject] = []
    for index, match in enumerate(matches):
        section = text[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()
        fields: dict[str, str] = {}
        aliases: list[str] = []
        evidence: list[str] = []
        list_field: str | None = None
        for line in section.splitlines()[1:]:
            field = _FIELD_RE.match(line)
            if field:
                key, field_value = field.group(1), (field.group(2) or "").strip()
                fields[key] = field_value
                list_field = key if key in {"Aliases", "Evidence"} else None
                continue
            if line.startswith("- ") and list_field == "Aliases":
                aliases.append(line[2:].strip())
            elif line.startswith("- ") and list_field == "Evidence":
                evidence.append(line[2:].strip())
            elif line.strip():
                list_field = None
        subjects.append(
            Subject(
                match.group(1),
                match.group(2).strip(),
                fields.get("Status", ""),
                fields.get("Kind", ""),
                fields.get("Canonical-Ref") or None,
                tuple(aliases),
                tuple(evidence),
                section,
                path,
            )
        )
    return subjects


def load_subjects(memory_dir: Path) -> list[Subject]:
    path = memory_dir / "subjects.md"
    if not path.exists():
        return []
    return parse_subjects(path, path.read_text(encoding="utf-8"))


def render_subject(
    subject_id: str,
    title: str,
    kind: str,
    canonical_ref: str | None,
    aliases: tuple[str, ...],
    evidence: tuple[str, ...],
) -> str:
    lines = [
        f"## {subject_id} — {' '.join(title.split())}",
        "",
        "Status: active",
        f"Kind: {kind}",
    ]
    if canonical_ref:
        lines.append(f"Canonical-Ref: {canonical_ref}")
    lines.extend(["Evidence:", *(f"- {item}" for item in evidence), "", "Aliases:"])
    lines.extend(f"- {item}" for item in aliases)
    return "\n".join(lines)


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


def validate_subject_registry(memory_dir: Path, project_root: Path) -> list[str]:
    path = memory_dir / "subjects.md"
    if not path.exists():
        return ["subjects.md: missing managed Subject registry"]
    subjects = load_subjects(memory_dir)
    issues: list[str] = []
    ids: dict[str, str] = {}
    aliases: dict[str, str] = {}
    refs: dict[str, str] = {}
    for subject in subjects:
        key = subject.subject_id.casefold()
        if key in ids:
            issues.append(f"subjects.md: duplicate Subject ID {subject.subject_id}")
        ids[key] = subject.subject_id
        if subject.status != "active":
            issues.append(f"subjects.md: {subject.subject_id} has invalid Status {subject.status!r}")
        try:
            validate_subject_kind(subject.kind)
        except ValueError as exc:
            issues.append(f"subjects.md: {subject.subject_id}: {exc}")
        try:
            validate_evidence(subject.evidence, project_root, allow_missing=True)
        except ValueError as exc:
            issues.append(f"subjects.md: {subject.subject_id}: {exc}")
        for alias in (subject.title, *subject.aliases):
            normalized = normalize_alias(alias)
            owner = aliases.get(normalized)
            if owner and owner.casefold() != subject.subject_id.casefold():
                issues.append(
                    f"subjects.md: normalized alias {alias!r} is owned by both {owner} and {subject.subject_id}"
                )
            aliases[normalized] = subject.subject_id
        if subject.canonical_ref:
            try:
                normalized_ref = normalize_canonical_ref(subject.canonical_ref)
            except ValueError as exc:
                issues.append(f"subjects.md: {subject.subject_id}: {exc}")
                continue
            owner = refs.get(normalized_ref)
            if owner and owner.casefold() != subject.subject_id.casefold():
                issues.append(
                    f"subjects.md: Canonical-Ref {normalized_ref!r} is owned by both {owner} and {subject.subject_id}"
                )
            refs[normalized_ref] = subject.subject_id
    return issues
