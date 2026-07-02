"""Shared protocol helpers for MemoryCustodian commands."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from typing import Iterable

from .templates import ALL_TEMPLATE_FILES, CORE_FILES, DEFAULT_MEMORY_DIR

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

COMMON_MEMORY_FILES = (
    "brief.md",
    "decisions.md",
    "constraints.md",
    "preferences.md",
    "inbox.md",
)

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def today() -> str:
    return date.today().isoformat()


def resolve_project_root(project_root: str | None) -> Path:
    return Path(project_root or ".").expanduser().resolve()


def resolve_memory_dir(project_root: Path, memory_dir: str | None = None) -> Path:
    memory = memory_dir or DEFAULT_MEMORY_DIR
    path = Path(memory).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


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
    append_text(path, entry)


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


def task_file_specs(task: str) -> list[tuple[str, bool]]:
    return TASK_FILE_MAP.get(task, TASK_FILE_MAP["default"])


def task_files(task: str) -> list[str]:
    return [name for name, _required in task_file_specs(task)]


def core_files() -> tuple[str, ...]:
    return CORE_FILES
