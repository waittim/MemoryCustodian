"""Forget memory entries and add tombstones."""

from __future__ import annotations

from pathlib import Path

from .protocol import append_changelog, append_text, iter_markdown_files, resolve_memory_dir, resolve_project_root, today, write_text


def _remove_topic(text: str, topic: str) -> tuple[str, int]:
    topic_lower = topic.lower()
    lines = text.splitlines()
    kept: list[str] = []
    removed = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if topic_lower in line.lower():
            removed += 1
            if line.startswith("## "):
                index += 1
                while index < len(lines) and not lines[index].startswith("## "):
                    index += 1
                continue
            index += 1
            continue
        kept.append(line)
        index += 1
    compacted = "\n".join(kept).rstrip() + "\n"
    compacted = compacted.replace("\n\n\n", "\n\n")
    return compacted, removed


def _target_files(memory_dir: Path, mode: str) -> list[Path]:
    include_archive = mode == "purge"
    files = [path for path in iter_markdown_files(memory_dir, include_archive=include_archive) if path.name != "do-not-use.md"]
    if mode == "soft":
        files = [path for path in files if path.name in {"brief.md", "decisions.md", "constraints.md", "preferences.md", "inbox.md"}]
    return files


def _tombstone(topic: str, mode: str) -> str:
    return (
        f"## Tombstone: {topic}\n"
        f"Do not reintroduce unless the user explicitly reverses this. "
        f"Reason: the user asked MemoryCustodian to forget this topic. Mode: {mode}. Date: {today()}."
    )


def _changelog_message(topic: str, mode: str) -> str:
    if mode == "soft":
        return f"Forgot topic '{topic}' with mode soft."
    return f"Completed {mode} forget operation."


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        return 1

    total_removed = 0
    changed_files: list[str] = []
    for path in _target_files(memory_dir, args.mode):
        original = path.read_text(encoding="utf-8")
        updated, removed = _remove_topic(original, args.topic)
        if removed:
            write_text(path, updated)
            total_removed += removed
            changed_files.append(str(path.relative_to(memory_dir)))

    append_text(memory_dir / "do-not-use.md", _tombstone(args.topic, args.mode))
    append_changelog(memory_dir, _changelog_message(args.topic, args.mode))

    print(f"Forgot topic: {args.topic}")
    print(f"Removed matches: {total_removed}")
    print("Changed files:")
    for name in changed_files:
        print(f"- {name}")
    print("- do-not-use.md")
    return 0
