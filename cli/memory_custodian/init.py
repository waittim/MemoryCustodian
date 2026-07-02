"""Initialize MemoryCustodian files in a project."""

from __future__ import annotations

from pathlib import Path

from .protocol import resolve_memory_dir, resolve_project_root, today, write_text
from .templates import CORE_FILES, OPTIONAL_FILES, render_template

CODEX_SNIPPET = """## MemoryCustodian

This project uses MemoryCustodian for local project memory.

Before substantial work:

1. Read `docs/memory/manifest.md`.
2. Read `docs/memory/brief.md`.
3. Load additional memory files only when the manifest says they are relevant.
4. Do not load `docs/memory/archive/` unless explicitly requested or performing memory maintenance.

Keep this file short. MemoryCustodian is the source of truth for durable project memory.
"""

CLAUDE_SNIPPET = """## MemoryCustodian

This project uses MemoryCustodian for local project memory.

Before substantial work:

1. Read `docs/memory/manifest.md`.
2. Read `docs/memory/brief.md`.
3. Load additional memory files only when the manifest says they are relevant.
4. Do not load `docs/memory/archive/` unless explicitly requested or performing memory maintenance.

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

    current_date = today()
    results: list[str] = []
    files = list(CORE_FILES)
    if args.extended:
        files.extend(OPTIONAL_FILES)
    for name in files:
        result = _write_if_needed(memory_dir / name, render_template(name, current_date), args.force)
        results.append(f"{name}: {result}")

    agent = args.agent
    with_codex = args.with_codex or agent in {"codex", "all"}
    with_claude = args.with_claude or agent in {"claude", "all"}
    if with_codex:
        result = _append_snippet(project_root / "AGENTS.md", CODEX_SNIPPET, args.force_agent)
        results.append(f"AGENTS.md: {result}")
    if with_claude:
        result = _append_snippet(project_root / "CLAUDE.md", CLAUDE_SNIPPET, args.force_agent)
        results.append(f"CLAUDE.md: {result}")

    print(f"Initialized MemoryCustodian at {memory_dir}")
    for item in results:
        print(f"- {item}")
    return 0
