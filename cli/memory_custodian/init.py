"""Initialize MemoryCustodian files in a project."""

from __future__ import annotations

from pathlib import Path

from .protocol import resolve_memory_dir, resolve_project_root, today, write_text
from .templates import CORE_FILES, OPTIONAL_FILES, render_template

BLOCK_START = "<!-- memory-custodian:start -->"
BLOCK_END = "<!-- memory-custodian:end -->"


def _memory_dir_label(project_root: Path, memory_dir: Path) -> str:
    try:
        return memory_dir.relative_to(project_root).as_posix()
    except ValueError:
        return memory_dir.as_posix()


def _agent_snippet(memory_label: str) -> str:
    return f"""{BLOCK_START}
## MemoryCustodian

This project uses MemoryCustodian for local project memory.

Before substantial work:

1. Read `{memory_label}/manifest.md`.
2. Read `{memory_label}/brief.md`.
3. Load additional memory files only when the manifest says they are relevant.
4. Do not load `{memory_label}/archive/` unless explicitly requested or performing memory maintenance.
5. After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose an update.

Keep this file short. MemoryCustodian is the source of truth for durable project memory.
{BLOCK_END}
"""


def _write_if_needed(path: Path, text: str, force: bool) -> str:
    if path.exists() and not force:
        return "kept"
    write_text(path, text)
    return "written"


def _append_snippet(path: Path, snippet: str, force: bool) -> str:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        starts = existing.count(BLOCK_START)
        ends = existing.count(BLOCK_END)
        if starts != ends:
            raise ValueError(f"{path.name}: malformed MemoryCustodian managed block; review incomplete markers")
        if starts > 1:
            raise ValueError(f"{path.name}: multiple MemoryCustodian managed blocks found; manual review required")
        if starts == 1:
            if not force:
                return "kept"
            start = existing.index(BLOCK_START)
            end = existing.index(BLOCK_END, start) + len(BLOCK_END)
            text = existing[:start] + snippet.strip() + existing[end:]
            write_text(path, text)
            return "written"

        legacy_count = existing.count("## MemoryCustodian")
        if legacy_count:
            if legacy_count > 1:
                raise ValueError(f"{path.name}: multiple unmanaged MemoryCustodian sections found; manual review required")
            if not force:
                return "kept (unmanaged legacy section)"
            start = existing.index("## MemoryCustodian")
            next_heading = existing.find("\n## ", start + len("## MemoryCustodian"))
            end = len(existing) if next_heading == -1 else next_heading + 1
            legacy = existing[start:end]
            if "This project uses MemoryCustodian" not in legacy or "manifest.md" not in legacy:
                raise ValueError(f"{path.name}: legacy MemoryCustodian section is not a recognized safe shape")
            text = existing[:start] + snippet.strip() + ("\n\n" if next_heading != -1 else "\n") + existing[end:]
            write_text(path, text)
            return "written"
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
    with_gemini = args.with_gemini or agent in {"gemini", "all"}
    if with_codex:
        result = _append_snippet(project_root / "AGENTS.md", _agent_snippet(memory_label), args.force_agent)
        results.append(f"AGENTS.md: {result}")
    if with_claude:
        result = _append_snippet(project_root / "CLAUDE.md", _agent_snippet(memory_label), args.force_agent)
        results.append(f"CLAUDE.md: {result}")
    if with_gemini:
        result = _append_snippet(project_root / "GEMINI.md", _agent_snippet(memory_label), args.force_agent)
        results.append(f"GEMINI.md: {result}")

    print(f"Initialized MemoryCustodian at {memory_dir}")
    for item in results:
        print(f"- {item}")
    if "brief.md: written" in results:
        print("Next: replace the brief.md TODOs with real project purpose, direction, and system context.")
    return 0
