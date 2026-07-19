"""Initialize MemoryCustodian files in a project."""

from __future__ import annotations

from pathlib import Path

from .mutations import TextMutation, apply_mutations
from .protocol import (
    is_indexable_optional_path,
    manifest_with_current_protocol_metadata,
    manifest_with_current_task_routing,
    manifest_with_optional_index,
    manifest_with_optional_module_index,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
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


def _snippet_update(path: Path, snippet: str, force: bool) -> tuple[str, str | None]:
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
                return "kept", None
            start = existing.index(BLOCK_START)
            end = existing.index(BLOCK_END, start) + len(BLOCK_END)
            text = existing[:start] + snippet.strip() + existing[end:]
            return "written", text

        legacy_count = existing.count("## MemoryCustodian")
        if legacy_count:
            if legacy_count > 1:
                raise ValueError(f"{path.name}: multiple unmanaged MemoryCustodian sections found; manual review required")
            if not force:
                return "kept (unmanaged legacy section)", None
            start = existing.index("## MemoryCustodian")
            next_heading = existing.find("\n## ", start + len("## MemoryCustodian"))
            end = len(existing) if next_heading == -1 else next_heading + 1
            legacy = existing[start:end]
            if "This project uses MemoryCustodian" not in legacy or "manifest.md" not in legacy:
                raise ValueError(f"{path.name}: legacy MemoryCustodian section is not a recognized safe shape")
            text = existing[:start] + snippet.strip() + ("\n\n" if next_heading != -1 else "\n") + existing[end:]
            return "written", text
        text = existing.rstrip() + "\n\n" + snippet.strip() + "\n"
    else:
        text = "# Agent Instructions\n\n" + snippet.strip() + "\n"
    return "written", text


def _repair_manifest(text: str) -> tuple[str, bool]:
    updated, metadata_changed = manifest_with_current_protocol_metadata(text)
    updated, routing_changed = manifest_with_current_task_routing(updated)
    updated, index_changed = manifest_with_optional_index(updated)
    return updated, metadata_changed or routing_changed or index_changed


def _index_existing_optional(memory_dir: Path, manifest: str) -> tuple[str, bool]:
    updated = manifest
    changed = False
    for folder in ("rules", "profiles", "areas"):
        directory = memory_dir / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            relative = path.relative_to(memory_dir).as_posix()
            if not is_indexable_optional_path(relative):
                continue
            updated, indexed = manifest_with_optional_module_index(updated, relative)
            changed = changed or indexed
    return updated, changed


def _looks_generated(name: str, text: str, rendered: str) -> bool:
    if text == rendered:
        return True
    normalized = text.strip()
    if name == "brief.md":
        return normalized.startswith("# Project Brief") and normalized.count("TODO:") >= 3
    known_empty = {
        "decisions.md": "# Decisions\n\nEntries are newest first.",
        "constraints.md": "# Constraints",
        "do-not-use.md": "# Do Not Use / Tombstones\n\nTombstones are newest first.",
        "inbox.md": "# Memory Inbox\n\nEntries are newest first.\n\nNo unprocessed memory candidates.",
        "preferences.md": "# Preferences\n\nSoft user or project preferences go here. Hard requirements belong in `constraints.md`.",
    }
    return normalized == known_empty.get(name)


def run(args) -> int:
    if args.force:
        raise ValueError(
            "init --force was removed because it could overwrite curated memory; use --repair, or preview `--replace-existing` and then add --apply"
        )
    if args.repair and args.replace_existing:
        raise ValueError("--repair and --replace-existing cannot be used together")
    if args.apply and not args.replace_existing:
        raise ValueError("--apply is only valid with --replace-existing")

    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.path or args.memory_dir)
    memory_label = _memory_dir_label(project_root, memory_dir)

    current_date = today()
    results: list[str] = []
    mutations: list[TextMutation] = []
    replacement_warnings: list[str] = []
    files = list(CORE_FILES)
    if args.extended:
        files.extend(OPTIONAL_FILES)
    for name in files:
        path = memory_dir / name
        rendered = render_template(name, current_date, memory_label)
        if not path.exists():
            result = "written"
            mutations.append(TextMutation(path, rendered))
        elif args.replace_existing:
            existing = path.read_text(encoding="utf-8")
            if name == "manifest.md":
                rendered, _indexed = _index_existing_optional(memory_dir, rendered)
            if existing == rendered:
                result = "kept (already current)"
            else:
                result = "replace planned"
                mutations.append(TextMutation(path, rendered))
                if not _looks_generated(name, existing, rendered):
                    replacement_warnings.append(name)
        elif args.repair and name == "manifest.md":
            repaired, changed = _repair_manifest(path.read_text(encoding="utf-8"))
            repaired, indexed = _index_existing_optional(memory_dir, repaired)
            changed = changed or indexed
            result = "repaired" if changed else "kept"
            if changed:
                mutations.append(TextMutation(path, repaired))
        else:
            result = "kept"
        results.append(f"{name}: {result}")

    agent = args.agent
    with_codex = args.with_codex or agent in {"codex", "all"}
    with_claude = args.with_claude or agent in {"claude", "all"}
    with_gemini = args.with_gemini or agent in {"gemini", "all"}
    if with_codex:
        path = project_root / "AGENTS.md"
        result, updated = _snippet_update(path, _agent_snippet(memory_label), args.force_agent or args.repair)
        if updated is not None:
            mutations.append(TextMutation(path, updated))
        results.append(f"AGENTS.md: {result}")
    if with_claude:
        path = project_root / "CLAUDE.md"
        result, updated = _snippet_update(path, _agent_snippet(memory_label), args.force_agent or args.repair)
        if updated is not None:
            mutations.append(TextMutation(path, updated))
        results.append(f"CLAUDE.md: {result}")
    if with_gemini:
        path = project_root / "GEMINI.md"
        result, updated = _snippet_update(path, _agent_snippet(memory_label), args.force_agent or args.repair)
        if updated is not None:
            mutations.append(TextMutation(path, updated))
        results.append(f"GEMINI.md: {result}")

    if args.replace_existing:
        print("MemoryCustodian replacement plan:")
        for item in results:
            print(f"- {item}")
        if replacement_warnings:
            print("Warning: these files contain non-template content and will be overwritten:")
            for name in replacement_warnings:
                print(f"- {name}")
        if not args.apply:
            print("Dry run only. Re-run with --replace-existing --apply only if full replacement is intended.")
            return 0

    apply_mutations(mutations)

    action = "Repaired" if args.repair else "Initialized"
    print(f"{action} MemoryCustodian at {memory_dir}")
    for item in results:
        print(f"- {item}")
    if "brief.md: written" in results:
        print("Next: replace the brief.md TODOs with real project purpose, direction, and system context.")
    return 0
