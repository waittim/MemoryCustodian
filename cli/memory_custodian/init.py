"""Initialize MemoryCustodian files in a project."""

from __future__ import annotations

from pathlib import Path

from .protocol import resolve_memory_dir, resolve_project_root, today, write_text
from .templates import CORE_FILES, OPTIONAL_FILES, render_template


def _memory_dir_label(project_root: Path, memory_dir: Path) -> str:
    try:
        return memory_dir.relative_to(project_root).as_posix()
    except ValueError:
        return memory_dir.as_posix()


def _agent_snippet(memory_label: str) -> str:
    return f"""## MemoryCustodian

This project uses MemoryCustodian for local project memory.

Before substantial work:

1. Read `{memory_label}/manifest.md`.
2. Read `{memory_label}/brief.md`.
3. Load additional memory files only when the manifest says they are relevant.
4. Do not load `{memory_label}/archive/` unless explicitly requested or performing memory maintenance.
5. After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose an update.

Keep this file short. MemoryCustodian is the source of truth for durable project memory.
"""


def _write_if_needed(path: Path, text: str, force: bool) -> str:
    if path.exists() and not force:
        return "kept"
    write_text(path, text)
    return "written"


def _append_snippet(path: Path, snippet: str, force: bool) -> str:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if "## MemoryCustodian" in existing and not force:
            return "kept"
        text = existing.rstrip() + "\n\n" + snippet.strip() + "\n"
    else:
        text = "# Agent Instructions\n\n" + snippet.strip() + "\n"
    write_text(path, text)
    return "written"


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.path or args.memory_dir)
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_label = _memory_dir_label(project_root, memory_dir)

    current_date = today()
    results: list[str] = []
    files = list(CORE_FILES)
    if args.extended:
        files.extend(OPTIONAL_FILES)
    for name in files:
        result = _write_if_needed(memory_dir / name, render_template(name, current_date, memory_label), args.force)
        results.append(f"{name}: {result}")

    agent = args.agent
    with_codex = args.with_codex or agent in {"codex", "all"}
    with_claude = args.with_claude or agent in {"claude", "all"}
    if with_codex:
        result = _append_snippet(project_root / "AGENTS.md", _agent_snippet(memory_label), args.force_agent)
        results.append(f"AGENTS.md: {result}")
    if with_claude:
        result = _append_snippet(project_root / "CLAUDE.md", _agent_snippet(memory_label), args.force_agent)
        results.append(f"CLAUDE.md: {result}")

    print(f"Initialized MemoryCustodian at {memory_dir}")
    for item in results:
        print(f"- {item}")
    return 0
