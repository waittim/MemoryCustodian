"""Shared protocol helpers for MemoryCustodian commands."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import re
import stat
import tempfile
from dataclasses import dataclass
from typing import Iterable

from . import __protocol_version__, __version__
from .templates import ALL_TEMPLATE_FILES, CORE_FILES, DEFAULT_MEMORY_DIR

DOCS_MEMORY_ROOT = "docs"
CURRENT_PACKAGE_LABEL = f"memory-custodian {__version__}"
CURRENT_PROTOCOL_VERSION = __protocol_version__

BUDGETS = {
    "brief.md": 500,
    "decisions.md": 800,
    "constraints.md": 400,
    "do-not-use.md": 400,
    "preferences.md": 300,
    "changelog.md": 800,
}

DECISION_ENTRY_BUDGET = 120

TASK_CATEGORY = {
    "default": "general", "general": "general",
    "planning": "planning", "architecture": "planning", "refactoring": "planning",
    "implementation": "implementation", "execution": "implementation", "debugging": "implementation",
    "artifact": "artifact", "output": "artifact", "preferences": "preferences",
    "recap": "history", "history": "history", "status": "history",
    "maintenance": "maintenance", "compact": "maintenance", "forget": "maintenance",
}

CATEGORY_HEADINGS = {
    "planning": {"planning / architecture / refactoring"},
    "implementation": {"implementation / execution / debugging"},
    "artifact": {"user-facing artifact / output"},
    "preferences": {"preferences"},
    "history": {"change history / recap"},
    "maintenance": {"memory maintenance"},
}

COMMON_MEMORY_FILES = (
    "brief.md",
    "decisions.md",
    "constraints.md",
    "preferences.md",
    "inbox.md",
)

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

OPTIONAL_INDEX_HEADING = "## Optional module index"
PROTOCOL_HEADING = "## MemoryCustodian Protocol"
PROTOCOL_SECTION_NAME = "memorycustodian protocol"
PROTOCOL_FIELD_RE = re.compile(r"^- ([A-Za-z_]+):\s*(.+)$")
OPTIONAL_INDEX_SECTIONS = {
    "rules": "### Enabled rules",
    "profiles": "### Enabled profiles",
    "areas": "### Enabled areas",
}
OPTIONAL_INDEX_TEMPLATE = """## Optional module index
Discover optional memory without loading it. Entries here are not default loads.

### Enabled rules
- None enabled.

### Enabled profiles
- None enabled.

### Enabled areas
- None enabled.
"""
OPTIONAL_INDEX_PATH_RE = re.compile(r"`((?:rules|profiles|areas)/[^`]+\.md)`")

LEGACY_IMPLEMENTATION_SECTION = """### Implementation / execution / debugging
Load:
- constraints.md
- do-not-use.md
Load if present:
- preferences.md
"""

CURRENT_IMPLEMENTATION_SECTION = """### Implementation / execution / debugging
Load:
- decisions.md
- constraints.md
- do-not-use.md
Load if present:
- preferences.md
"""

DEFAULT_OPTIONAL_TRIGGERS = {
    "rules/output.md": "Load for user-facing artifacts, publishable text, or copied output.",
    "rules/code-style.md": "Load when writing, reviewing, or refactoring code style.",
    "rules/safety.md": "Load when safety-sensitive behavior, secrets, privacy, or permissions matter.",
    "rules/review.md": "Load when performing code or document review.",
    "profiles/git.md": "Load for branch, commit, merge, rebase, PR, or release-tag workflow tasks.",
    "profiles/docs.md": "Load for documentation writing, editing, or publishing workflows.",
    "profiles/release.md": "Load for release planning, changelogs, versioning, or packaging workflows.",
    "profiles/tickets.md": "Load for issue, ticket, backlog, or project-tracking workflows.",
    "profiles/research.md": "Load for research, source comparison, citations, or evidence-heavy tasks.",
    "areas/frontend.md": "Load when touching UI, routes, client state, styling, browser behavior, or frontend tests.",
    "areas/backend.md": "Load when touching APIs, persistence, services, CLI internals, or backend tests.",
    "areas/infra.md": "Load when touching deployment, CI, environments, dependencies, or operational config.",
}


def today() -> str:
    return date.today().isoformat()


def resolve_project_root(project_root: str | None) -> Path:
    return Path(project_root or ".").expanduser().resolve()


def resolve_memory_dir(project_root: Path, memory_dir: str | None = None) -> Path:
    memory = memory_dir or DEFAULT_MEMORY_DIR
    path = Path(memory).expanduser()
    if not path.is_absolute():
        path = project_root / path
    resolved = path.resolve()
    docs_root = (project_root / DOCS_MEMORY_ROOT).resolve()
    try:
        relative = resolved.relative_to(docs_root)
    except ValueError as exc:
        raise ValueError("Memory directory must live under docs/, such as docs/memory.") from exc
    if not relative.parts:
        raise ValueError("Memory directory must be a subdirectory of docs/, such as docs/memory.")
    return resolved


def ensure_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def estimate_tokens(text: str) -> int:
    # Cheap approximation that works offline and treats punctuation/CJK as tokens.
    return len(re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", text))


def parse_version(value: str) -> tuple[int, ...] | None:
    parts = value.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def compare_versions(left: str, right: str) -> int | None:
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    if left_parts is None or right_parts is None:
        return None
    width = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (width - len(left_parts))
    padded_right = right_parts + (0,) * (width - len(right_parts))
    if padded_left < padded_right:
        return -1
    if padded_left > padded_right:
        return 1
    return 0


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(ensure_newline(text))
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def append_text(path: Path, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    write_text(path, appended_text(existing, text))


def appended_text(existing: str, text: str) -> str:
    if existing:
        return existing.rstrip() + "\n\n" + text.strip() + "\n"
    return text.strip() + "\n"


def prepend_text(path: Path, text: str, remove_lines: tuple[str, ...] = ()) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    write_text(path, prepended_text(existing, text, remove_lines))


def prepended_text(existing: str, text: str, remove_lines: tuple[str, ...] = ()) -> str:
    if not existing:
        return text.strip() + "\n"

    lines = [line for line in existing.rstrip().splitlines() if line.strip() not in remove_lines]
    insert_at = 0
    if lines and lines[0].startswith("# "):
        insert_at = 1
        while insert_at < len(lines):
            stripped = lines[insert_at].strip()
            if lines[insert_at].startswith("## ") or stripped.startswith("- "):
                break
            insert_at += 1

    before = "\n".join(lines[:insert_at]).rstrip()
    after = "\n".join(lines[insert_at:]).strip()
    entry = text.strip()
    if before and after:
        return f"{before}\n\n{entry}\n\n{after}\n"
    elif before:
        return f"{before}\n\n{entry}\n"
    elif after:
        return f"{entry}\n\n{after}\n"
    return entry + "\n"


def append_changelog(memory_dir: Path, message: str, create: bool = False) -> None:
    path = memory_dir / "changelog.md"
    if not path.exists() and not create:
        return
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    write_text(path, changelog_text(existing, message))


def changelog_text(existing: str, message: str) -> str:
    entry = f"## {today()}\n- {message}"
    existing = existing.rstrip()
    if not existing:
        return "# Memory Changelog\n\n" + entry + "\n"

    lines = existing.splitlines()
    insert_at = 0
    if lines and lines[0].strip() == "# Memory Changelog":
        insert_at = len(lines)
        for index, line in enumerate(lines[1:], start=1):
            if line.startswith("## "):
                insert_at = index
                break

    before = "\n".join(lines[:insert_at]).rstrip()
    after = "\n".join(lines[insert_at:]).strip()
    if before and after:
        return f"{before}\n\n{entry}\n\n{after}\n"
    elif before:
        return f"{before}\n\n{entry}\n"
    elif after:
        return f"{entry}\n\n{after}\n"
    return entry + "\n"


def protocol_metadata(manifest: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    lines = _section_lines(manifest, "##", lambda heading: heading == PROTOCOL_SECTION_NAME)
    for line in lines:
        match = PROTOCOL_FIELD_RE.match(line.strip())
        if match:
            metadata[match.group(1)] = match.group(2).strip()
    return metadata


def _protocol_section_lines(initialized_with: str, last_migrated_with: str) -> list[str]:
    return [
        PROTOCOL_HEADING,
        f"- protocol_version: {CURRENT_PROTOCOL_VERSION}",
        f"- initialized_with: {initialized_with}",
        f"- last_migrated_with: {last_migrated_with}",
    ]


def manifest_with_protocol_metadata(manifest: str, last_migrated_with: str = CURRENT_PACKAGE_LABEL) -> tuple[str, bool]:
    metadata = protocol_metadata(manifest)
    initialized_with = metadata.get("initialized_with", "unknown")
    replacement = _protocol_section_lines(initialized_with, last_migrated_with)
    lines = manifest.splitlines()

    for index, line in enumerate(lines):
        if line.strip() == PROTOCOL_HEADING:
            end = len(lines)
            for next_index in range(index + 1, len(lines)):
                if lines[next_index].startswith("## "):
                    end = next_index
                    break
            desired = {
                "protocol_version": f"- protocol_version: {CURRENT_PROTOCOL_VERSION}",
                "initialized_with": f"- initialized_with: {initialized_with}",
                "last_migrated_with": f"- last_migrated_with: {last_migrated_with}",
            }
            body: list[str] = []
            seen: set[str] = set()
            for existing_line in lines[index + 1 : end]:
                match = PROTOCOL_FIELD_RE.match(existing_line.strip())
                key = match.group(1) if match else None
                if key in desired:
                    if key not in seen:
                        body.append(desired[key])
                        seen.add(key)
                    continue
                body.append(existing_line)
            missing = [desired[key] for key in ("protocol_version", "initialized_with", "last_migrated_with") if key not in seen]
            updated = lines[: index + 1] + missing + body + lines[end:]
            text = ensure_newline("\n".join(updated))
            return text, text != ensure_newline(manifest)

    insert_at = len(lines)
    for index, line in enumerate(lines):
        if line.startswith("## "):
            insert_at = index
            break
    updated = lines[:insert_at] + [""] + replacement + [""] + lines[insert_at:]
    text = ensure_newline("\n".join(updated).replace("\n\n\n", "\n\n"))
    return text, text != ensure_newline(manifest)


def manifest_with_current_protocol_metadata(manifest: str) -> tuple[str, bool]:
    return manifest_with_protocol_metadata(manifest, CURRENT_PACKAGE_LABEL)


def manifest_with_current_task_routing(manifest: str) -> tuple[str, bool]:
    """Upgrade the generated 0.4 implementation route without overriding custom manifests."""

    if CURRENT_IMPLEMENTATION_SECTION in manifest:
        return manifest, False
    if LEGACY_IMPLEMENTATION_SECTION not in manifest:
        return manifest, False
    updated = manifest.replace(LEGACY_IMPLEMENTATION_SECTION, CURRENT_IMPLEMENTATION_SECTION, 1)
    return ensure_newline(updated), True


def existing_memory_files(memory_dir: Path) -> list[Path]:
    return [memory_dir / name for name in ALL_TEMPLATE_FILES if (memory_dir / name).exists()]


def iter_markdown_files(memory_dir: Path, include_archive: bool = False) -> Iterable[Path]:
    for name in ALL_TEMPLATE_FILES:
        if name.startswith("archive/") and not include_archive:
            continue
        path = memory_dir / name
        if path.exists():
            yield path
    for folder in ("rules", "profiles", "areas"):
        directory = memory_dir / folder
        if directory.exists():
            for path in sorted(directory.glob("*.md")):
                if path.name != "README.md":
                    yield path
    archive = memory_dir / "archive"
    if include_archive and archive.exists():
        yield from sorted(archive.rglob("*.md"))


def count_inbox_items(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("- "))


def count_h2_entries(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("## "))


def decision_entry_sizes(text: str) -> list[tuple[str, int]]:
    """Return titles and token sizes for H2 sections that contain a Decision field."""

    lines = text.rstrip().splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    entries: list[tuple[str, int]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        section = lines[start:end]
        if not any(line.strip() == "Decision:" for line in section[1:]):
            continue
        title = section[0][3:].strip()
        entries.append((title, estimate_tokens("\n".join(section))))
    return entries


def long_decision_entries(text: str, budget: int = DECISION_ENTRY_BUDGET) -> list[tuple[str, int]]:
    return [(title, tokens) for title, tokens in decision_entry_sizes(text) if tokens > budget]


def budget_for(name: str) -> int | None:
    if name.startswith("rules/"):
        return 400
    if name.startswith("profiles/"):
        return 500
    if name.startswith("areas/"):
        return 600
    return BUDGETS.get(name)


@dataclass(frozen=True)
class MarkdownUnit:
    kind: str
    text: str
    heading: str | None = None


@dataclass(frozen=True)
class MarkdownDocument:
    title: str
    units: tuple[MarkdownUnit, ...]


def parse_markdown_units(text: str) -> MarkdownDocument:
    """Parse the narrow Markdown structures managed by MemoryCustodian."""

    lines = text.rstrip().splitlines()
    title = lines[0] if lines and lines[0].startswith("# ") else ""
    start = 1 if title else 0
    h2_starts = [index for index in range(start, len(lines)) if lines[index].startswith("## ")]
    units: list[MarkdownUnit] = []
    if h2_starts:
        preamble = "\n".join(lines[start:h2_starts[0]]).strip()
        if preamble:
            units.append(MarkdownUnit("preamble", preamble))
        for position, unit_start in enumerate(h2_starts):
            unit_end = h2_starts[position + 1] if position + 1 < len(h2_starts) else len(lines)
            unit_text = "\n".join(lines[unit_start:unit_end]).strip()
            units.append(MarkdownUnit("h2", unit_text, lines[unit_start][3:].strip()))
        return MarkdownDocument(title, tuple(units))

    bullet_starts = [index for index in range(start, len(lines)) if lines[index].startswith(('- ', '* ', '+ '))]
    if bullet_starts:
        preamble = "\n".join(lines[start:bullet_starts[0]]).strip()
        if preamble:
            units.append(MarkdownUnit("preamble", preamble))
        for position, unit_start in enumerate(bullet_starts):
            unit_end = bullet_starts[position + 1] if position + 1 < len(bullet_starts) else len(lines)
            unit_text = "\n".join(lines[unit_start:unit_end]).strip()
            units.append(MarkdownUnit("bullet", unit_text))
        return MarkdownDocument(title, tuple(units))

    body = "\n".join(lines[start:]).strip()
    if body:
        units.append(MarkdownUnit("body", body))
    return MarkdownDocument(title, tuple(units))


def render_markdown_document(document: MarkdownDocument, units: Iterable[MarkdownUnit] | None = None) -> str:
    parts = [document.title] if document.title else []
    parts.extend(unit.text for unit in (document.units if units is None else units) if unit.text.strip())
    return ensure_newline("\n\n".join(parts))


def pack_to_budget(text: str, budget: int | None) -> tuple[str, int, bool]:
    """Pack complete units and return text, omitted count, oversized-unit warning."""

    normalized = text.strip()
    if budget is None or estimate_tokens(normalized) <= budget:
        return normalized, 0, False
    document = parse_markdown_units(normalized)
    chosen: list[MarkdownUnit] = []
    oversized = False
    for index, unit in enumerate(document.units):
        candidate = render_markdown_document(document, [*chosen, unit]).strip()
        if estimate_tokens(candidate) <= budget:
            chosen.append(unit)
            continue
        first_semantic = unit.kind != "preamble" and not any(item.kind != "preamble" for item in chosen)
        if not chosen or first_semantic:
            chosen.append(unit)
            oversized = True
        return render_markdown_document(document, chosen).strip(), len(document.units) - len(chosen), oversized
    return render_markdown_document(document, chosen).strip(), 0, oversized


def is_safe_memory_name(name: str) -> bool:
    return bool(SAFE_NAME_RE.fullmatch(name))


def optional_index_paths(manifest: str) -> set[str]:
    lines = _section_lines(manifest, "##", lambda heading: heading == "optional module index")
    return set(OPTIONAL_INDEX_PATH_RE.findall("\n".join(lines)))


def manifest_with_optional_index(manifest: str) -> tuple[str, bool]:
    updated, changed = _insert_optional_index(manifest)
    for heading in OPTIONAL_INDEX_SECTIONS.values():
        updated, subsection_changed = _ensure_optional_index_subsection(updated, heading)
        changed = changed or subsection_changed
    return updated, changed


def is_indexable_optional_path(relative_path: str) -> bool:
    parts = relative_path.split("/", 1)
    if len(parts) != 2:
        return False
    folder, name = parts
    return folder in OPTIONAL_INDEX_SECTIONS and name != "README.md" and name.endswith(".md")


def default_optional_trigger(relative_path: str) -> str:
    if relative_path in DEFAULT_OPTIONAL_TRIGGERS:
        return DEFAULT_OPTIONAL_TRIGGERS[relative_path]
    folder, _name = relative_path.split("/", 1)
    if folder == "rules":
        return "Load when this task-specific rule clearly matches the current task."
    if folder == "profiles":
        return "Load when this workflow clearly matches the current task or the user explicitly requests it."
    return "Load when touched files or task scope clearly match this area or the user explicitly requests it."


def _insert_optional_index(manifest: str) -> tuple[str, bool]:
    if OPTIONAL_INDEX_HEADING in manifest:
        return manifest, False
    insertion = "\n" + OPTIONAL_INDEX_TEMPLATE.strip() + "\n"
    for marker in ("## Optional profiles", "## Area-specific memory", "## Explicit only", "## Context budget"):
        index = manifest.find(marker)
        if index != -1:
            prefix = manifest[:index].rstrip()
            suffix = manifest[index:].lstrip()
            return prefix + "\n\n" + insertion.strip() + "\n\n" + suffix, True
    return manifest.rstrip() + "\n\n" + insertion.strip() + "\n", True


def _ensure_optional_index_subsection(manifest: str, heading: str) -> tuple[str, bool]:
    if heading in manifest:
        return manifest, False
    index = manifest.find(OPTIONAL_INDEX_HEADING)
    if index == -1:
        return manifest, False
    next_major = manifest.find("\n## ", index + len(OPTIONAL_INDEX_HEADING))
    insert_at = len(manifest) if next_major == -1 else next_major
    prefix = manifest[:insert_at].rstrip()
    suffix = manifest[insert_at:].lstrip()
    inserted = f"{heading}\n- None enabled.\n"
    return prefix + "\n\n" + inserted + ("\n" + suffix if suffix else ""), True


def manifest_with_optional_module_index(manifest: str, relative_path: str) -> tuple[str, bool]:
    if not is_indexable_optional_path(relative_path):
        return manifest, False
    manifest, changed = _insert_optional_index(manifest)
    folder = relative_path.split("/", 1)[0]
    heading = OPTIONAL_INDEX_SECTIONS[folder]
    manifest, subsection_changed = _ensure_optional_index_subsection(manifest, heading)
    changed = changed or subsection_changed

    if relative_path in optional_index_paths(manifest):
        return manifest, changed

    lines = manifest.splitlines()
    try:
        heading_index = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return manifest, changed

    end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("### ") or stripped.startswith("## "):
            end = index
            break

    entry = f"- `{relative_path}`: {default_optional_trigger(relative_path)}"
    subsection = [line for line in lines[heading_index + 1 : end] if line.strip() != "- None enabled."]
    lines = lines[: heading_index + 1] + [entry] + subsection + lines[end:]
    return ensure_newline("\n".join(lines)), True


def _normalize_heading(text: str) -> str:
    return text.strip().strip("#").strip().casefold()


def _section_lines(manifest: str, heading_level: str, matcher) -> list[str]:
    lines = manifest.splitlines()
    captured: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(heading_level + " "):
            if in_section:
                break
            in_section = matcher(_normalize_heading(stripped))
            continue
        if in_section and stripped.startswith("#" * len(heading_level) + " "):
            break
        if in_section:
            captured.append(line)
    return captured


def _parse_bullets(lines: list[str], default_required: bool) -> list[tuple[str, bool]]:
    specs: list[tuple[str, bool]] = []
    required = default_required
    for line in lines:
        stripped = line.strip()
        lowered = stripped.casefold()
        if lowered in {"load:", "also load:"}:
            required = True
            continue
        if lowered == "load if present:":
            required = False
            continue
        if not stripped.startswith("- "):
            continue
        name = stripped[2:].strip().strip("`")
        if name and not name.endswith("/"):
            specs.append((name, required))
    return specs


def _dedupe_specs(specs: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    seen: dict[str, bool] = {}
    order: list[str] = []
    for name, required in specs:
        if name not in seen:
            order.append(name)
            seen[name] = required
        else:
            seen[name] = seen[name] or required
    return [(name, seen[name]) for name in order]


def _route_sections(manifest: str) -> dict[str, list[tuple[str, list[str]]]]:
    sections = {category: [] for category in CATEGORY_HEADINGS}
    lines = manifest.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("### "):
            continue
        heading = _normalize_heading(line)
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            if lines[next_index].strip().startswith(("### ", "## ")):
                end = next_index
                break
        for category, aliases in CATEGORY_HEADINGS.items():
            if heading in aliases:
                sections[category].append((heading, lines[index + 1:end]))
    return sections


def _validate_route_path(name: str) -> str | None:
    path = Path(name)
    if not name or path.is_absolute() or "\\" in name or ":" in path.parts[0] or ".." in path.parts or path.suffix != ".md":
        return f"unsafe or malformed memory path {name!r}"
    if any(part in {"", "."} for part in path.parts):
        return f"unsafe or malformed memory path {name!r}"
    return None


def validate_manifest_routes(manifest: str) -> list[str]:
    issues: list[str] = []
    always_matches = []
    lines = manifest.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("## ") and _normalize_heading(line) == "always load":
            end = next((i for i in range(index + 1, len(lines)) if lines[i].strip().startswith("## ")), len(lines))
            always_matches.append(lines[index + 1:end])
    if len(always_matches) != 1:
        issues.append(f"general route: expected exactly one 'Always load' section, found {len(always_matches)}")
    sections = _route_sections(manifest)
    for category, matches in sections.items():
        if len(matches) != 1:
            candidates = ", ".join(repr(heading) for heading, _lines in matches) or "none"
            issues.append(f"{category} route: expected one canonical heading; candidates: {candidates}")
    route_lines = [("general", section) for section in always_matches]
    route_lines.extend((category, match[0][1]) for category, match in sections.items() if len(match) == 1)
    for category, section_lines in route_lines:
        for name, _required in _parse_bullets(section_lines, True):
            error = _validate_route_path(name)
            if error:
                issues.append(f"{category} route: {error}")
    if len(always_matches) == 1:
        always_specs = _parse_bullets(always_matches[0], True)
        for category, matches in sections.items():
            if len(matches) != 1:
                continue
            names = [name for name, _required in [*always_specs, *_parse_bullets(matches[0][1], True)]]
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                issues.append(f"{category} route: duplicate paths: {', '.join(duplicates)}")
    return issues


def parse_manifest_task_file_specs(manifest: str, task: str) -> list[tuple[str, bool]]:
    category = TASK_CATEGORY.get(task)
    if category is None:
        raise ValueError(f"Unsupported task route: {task}")
    issues = validate_manifest_routes(manifest)
    category_issues = [
        issue for issue in issues
        if issue.startswith(("general route: expected", f"{category} route: expected"))
        or issue.startswith(("general route: unsafe", f"{category} route: unsafe"))
    ]
    if category_issues:
        raise ValueError("Invalid manifest routing: " + "; ".join(category_issues))
    always_lines = _section_lines(manifest, "##", lambda heading: heading == "always load")
    specs = _parse_bullets(always_lines, default_required=True)
    if category != "general":
        match = _route_sections(manifest)[category][0]
        specs.extend(_parse_bullets(match[1], default_required=True))
    for name, _required in specs:
        error = _validate_route_path(name)
        if error:
            raise ValueError(error)
    return _dedupe_specs(specs)


def manifest_task_file_specs(memory_dir: Path, task: str) -> list[tuple[str, bool]]:
    manifest = memory_dir / "manifest.md"
    if not manifest.exists():
        raise ValueError(
            "manifest.md is missing; restore it, apply an applicable migration, or carefully reinitialize the project"
        )
    return parse_manifest_task_file_specs(manifest.read_text(encoding="utf-8"), task)


def resolve_manifest_memory_path(memory_dir: Path, name: str) -> Path:
    error = _validate_route_path(name)
    if error:
        raise ValueError(error)
    path = memory_dir / name
    try:
        path.resolve().relative_to(memory_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"memory path escapes the configured memory directory: {name!r}") from exc
    return path


def core_files() -> tuple[str, ...]:
    return CORE_FILES
