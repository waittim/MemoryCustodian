"""Shared protocol helpers for MemoryCustodian commands."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from typing import Iterable

from .templates import ALL_TEMPLATE_FILES, CORE_FILES, DEFAULT_MEMORY_DIR

DOCS_MEMORY_ROOT = "docs"

BUDGETS = {
    "brief.md": 500,
    "decisions.md": 800,
    "constraints.md": 400,
    "do-not-use.md": 400,
    "preferences.md": 300,
    "changelog.md": 800,
}

TASK_FILE_MAP = {
    "default": [("brief.md", True)],
    "general": [("brief.md", True)],
    "planning": [("brief.md", True), ("decisions.md", True), ("constraints.md", True), ("do-not-use.md", True)],
    "architecture": [("brief.md", True), ("decisions.md", True), ("constraints.md", True), ("do-not-use.md", True)],
    "refactoring": [("brief.md", True), ("decisions.md", True), ("constraints.md", True), ("do-not-use.md", True)],
    "implementation": [("brief.md", True), ("constraints.md", True), ("do-not-use.md", True), ("preferences.md", False)],
    "execution": [("brief.md", True), ("constraints.md", True), ("do-not-use.md", True), ("preferences.md", False)],
    "debugging": [("brief.md", True), ("constraints.md", True), ("do-not-use.md", True), ("preferences.md", False)],
    "artifact": [("brief.md", True), ("rules/output.md", False), ("preferences.md", False), ("do-not-use.md", True)],
    "output": [("brief.md", True), ("rules/output.md", False), ("preferences.md", False), ("do-not-use.md", True)],
    "preferences": [("brief.md", True), ("preferences.md", False)],
    "recap": [("brief.md", True), ("decisions.md", True), ("changelog.md", False)],
    "history": [("brief.md", True), ("decisions.md", True), ("changelog.md", False)],
    "maintenance": [("brief.md", True), ("inbox.md", True), ("do-not-use.md", True), ("changelog.md", False)],
    "status": [("brief.md", True), ("changelog.md", False)],
    "compact": [
        ("brief.md", True),
        ("inbox.md", True),
        ("decisions.md", True),
        ("constraints.md", True),
        ("do-not-use.md", True),
        ("preferences.md", False),
        ("changelog.md", False),
    ],
    "forget": [
        ("brief.md", True),
        ("decisions.md", True),
        ("constraints.md", True),
        ("do-not-use.md", True),
        ("preferences.md", False),
        ("inbox.md", True),
        ("changelog.md", False),
    ],
}

TASK_SECTION_KEYWORDS = {
    "planning": ("planning", "architecture", "refactoring"),
    "architecture": ("planning", "architecture", "refactoring"),
    "refactoring": ("planning", "architecture", "refactoring"),
    "implementation": ("implementation", "execution", "debugging"),
    "execution": ("implementation", "execution", "debugging"),
    "debugging": ("implementation", "execution", "debugging"),
    "artifact": ("artifact", "user-facing", "output"),
    "output": ("artifact", "user-facing", "output"),
    "preferences": ("preference", "preferences"),
    "recap": ("change history", "project recap", "history", "recap"),
    "history": ("change history", "project recap", "history", "recap"),
    "status": ("change history", "project recap", "history", "recap", "status"),
    "maintenance": ("memory maintenance", "maintenance"),
    "compact": ("memory maintenance", "maintenance"),
    "forget": ("memory maintenance", "maintenance"),
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
OPTIONAL_INDEX_SECTIONS = {
    "rules": "### Enabled rules",
    "profiles": "### Enabled profiles",
    "areas": "### Enabled areas",
}
OPTIONAL_INDEX_TEMPLATE = """## Optional module index
Agents use this lightweight index to discover optional memory without loading its contents. Entries here are not default loads; load the referenced file only when the trigger applies.

### Enabled rules
- None enabled.

### Enabled profiles
- None enabled.

### Enabled areas
- None enabled.
"""
OPTIONAL_INDEX_PATH_RE = re.compile(r"`((?:rules|profiles|areas)/[^`]+\.md)`")

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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ensure_newline(text), encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing:
        write_text(path, existing.rstrip() + "\n\n" + text.strip() + "\n")
    else:
        write_text(path, text.strip() + "\n")


def append_changelog(memory_dir: Path, message: str, create: bool = False) -> None:
    path = memory_dir / "changelog.md"
    if not path.exists() and not create:
        return
    entry = f"## {today()}\n- {message}"
    if not path.exists():
        write_text(path, "# Memory Changelog\n\n" + entry + "\n")
        return
    existing = path.read_text(encoding="utf-8").rstrip()
    if not existing:
        write_text(path, "# Memory Changelog\n\n" + entry + "\n")
        return

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
        write_text(path, f"{before}\n\n{entry}\n\n{after}\n")
    elif before:
        write_text(path, f"{before}\n\n{entry}\n")
    elif after:
        write_text(path, f"{entry}\n\n{after}\n")
    else:
        write_text(path, entry + "\n")


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


def budget_for(name: str) -> int | None:
    if name.startswith("rules/"):
        return 400
    if name.startswith("profiles/"):
        return 500
    if name.startswith("areas/"):
        return 600
    return BUDGETS.get(name)


def trim_to_budget(text: str, budget: int | None) -> tuple[str, bool]:
    if budget is None:
        return text, False
    matches = list(re.finditer(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", text))
    if len(matches) <= budget:
        return text, False
    cutoff = matches[budget].start()
    trimmed = text[:cutoff].rstrip()
    return trimmed + f"\n\n[Trimmed to {budget} token budget.]", True


def is_safe_memory_name(name: str) -> bool:
    return bool(SAFE_NAME_RE.fullmatch(name))


def optional_index_paths(manifest: str) -> set[str]:
    lines = _section_lines(manifest, "##", lambda heading: heading == "optional module index")
    return set(OPTIONAL_INDEX_PATH_RE.findall("\n".join(lines)))


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


def task_file_specs(task: str) -> list[tuple[str, bool]]:
    return TASK_FILE_MAP.get(task, TASK_FILE_MAP["default"])


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


def parse_manifest_task_file_specs(manifest: str, task: str) -> list[tuple[str, bool]]:
    always_lines = _section_lines(manifest, "##", lambda heading: heading == "always load")
    specs = _parse_bullets(always_lines, default_required=True)

    keywords = TASK_SECTION_KEYWORDS.get(task, ())
    if keywords:
        task_lines = _section_lines(manifest, "###", lambda heading: any(keyword in heading for keyword in keywords))
        specs.extend(_parse_bullets(task_lines, default_required=True))

    return _dedupe_specs(specs)


def manifest_task_file_specs(memory_dir: Path, task: str) -> list[tuple[str, bool]]:
    manifest = memory_dir / "manifest.md"
    if not manifest.exists():
        return task_file_specs(task)
    specs = parse_manifest_task_file_specs(manifest.read_text(encoding="utf-8"), task)
    if not specs:
        return task_file_specs(task)
    return specs


def task_files(task: str) -> list[str]:
    return [name for name, _required in task_file_specs(task)]


def core_files() -> tuple[str, ...]:
    return CORE_FILES
