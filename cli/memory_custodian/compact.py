"""Compact deterministic inbox entries."""

from __future__ import annotations

from .protocol import append_changelog, append_text, resolve_memory_dir, resolve_project_root, today, write_text
from .templates import render_template


def _extract_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if item:
                items.append(item)
    return items


def _classify(item: str) -> str | None:
    lower = item.lower()
    if any(token in lower for token in ("do not", "don't", "not use", "rejected", "avoid")):
        return "do-not-use.md"
    if any(token in lower for token in ("decided", "decision", "chose", "chosen")):
        return "decisions.md"
    if any(token in lower for token in ("must", "constraint", "required", "requirement")):
        return "constraints.md"
    if any(token in lower for token in ("prefer", "preference", "wants", "style")):
        return "preferences.md"
    return None


def _format_for(target: str, item: str) -> str:
    if target == "decisions.md":
        return f"## {today()} - {item[:72]}\nDecision:\n{item}\nReason:\nCompacted from memory inbox."
    if target == "do-not-use.md":
        return (
            f"## Tombstone: {item[:72]}\n"
            f"Do not reintroduce unless the user explicitly reverses this. "
            f"Reason: compacted from memory inbox. Date: {today()}."
        )
    return f"- {item}"


def _ensure_destination(memory_dir, target: str) -> None:
    path = memory_dir / target
    if path.exists():
        return
    if target == "preferences.md":
        write_text(path, render_template("preferences.md", today()))
    elif target == "changelog.md":
        write_text(path, render_template("changelog.md", today()))


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    inbox = memory_dir / "inbox.md"
    if not inbox.exists():
        print(f"Inbox not found: {inbox}")
        return 1

    original = inbox.read_text(encoding="utf-8")
    tombstones = (memory_dir / "do-not-use.md").read_text(encoding="utf-8").casefold() if (memory_dir / "do-not-use.md").exists() else ""
    items = _extract_items(original)
    seen: set[str] = set()
    deduped: list[str] = []
    duplicates = 0
    for item in items:
        key = item.casefold()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        deduped.append(item)

    classified: dict[str, list[str]] = {}
    remaining: list[str] = []
    for item in deduped:
        if item.casefold() in tombstones:
            continue
        target = _classify(item)
        if target is None:
            remaining.append(item)
        else:
            classified.setdefault(target, []).append(item)

    print("# Compaction Plan")
    print(f"Inbox items: {len(items)}")
    print(f"Duplicates: {duplicates}")
    for target, values in classified.items():
        print(f"{target}: {len(values)} candidate(s)")
    print(f"Remaining inbox items: {len(remaining)}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to write deterministic changes.")
        return 0

    for target, values in classified.items():
        _ensure_destination(memory_dir, target)
        for item in values:
            append_text(memory_dir / target, _format_for(target, item))

    new_inbox = "# Memory Inbox\n\n"
    if remaining:
        new_inbox += f"## {today()}\n" + "\n".join(f"- {item}" for item in remaining) + "\n"
    else:
        new_inbox += "No unprocessed memory candidates.\n"
    write_text(inbox, new_inbox)
    append_changelog(memory_dir, f"Compacted inbox: moved {sum(len(v) for v in classified.values())} item(s), removed {duplicates} duplicate(s).")
    print("Applied compaction.")
    return 0
