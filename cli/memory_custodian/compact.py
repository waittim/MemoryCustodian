"""Compact deterministic inbox entries."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from .protocol import (
    append_changelog,
    append_text,
    budget_for,
    estimate_tokens,
    prepend_text,
    resolve_memory_dir,
    resolve_project_root,
    today,
    write_text,
)
from .templates import render_template

ARCHIVABLE_H2_TARGETS = {"decisions.md", "changelog.md"}
BULLET_DEDUPE_TARGETS = {"constraints.md", "preferences.md"}
MANUAL_TARGET_REASONS = {
    "brief.md": "brief.md is the current one-screen summary; rewrite it semantically instead of archiving old lines.",
    "do-not-use.md": "do-not-use.md tombstones remain active; consolidate or shorten them instead of archiving them away.",
}


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


def _normalize_target(target: str) -> str:
    normalized = target.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Target must be a memory file path under docs/memory, such as decisions.md.")
    if not normalized.endswith(".md"):
        raise ValueError("Target must be a Markdown memory file.")
    if normalized == "manifest.md":
        raise ValueError("manifest.md defines loading policy and is not compacted by this command.")
    if normalized == "inbox.md":
        raise ValueError("Use `memory-custodian compact` without --target to compact inbox.md.")
    if normalized.startswith("archive/"):
        raise ValueError("archive/ is explicit-only and is not compacted by this command.")
    if budget_for(normalized) is None:
        raise ValueError(f"{normalized} has no context budget to compact against.")
    return normalized


def _target_path(memory_dir: Path, target: str) -> tuple[str, Path]:
    normalized = _normalize_target(target)
    return normalized, memory_dir.joinpath(*PurePosixPath(normalized).parts)


def _dedupe_bullets(text: str) -> tuple[str, int]:
    seen: set[str] = set()
    removed = 0
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            key = stripped.casefold()
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n", removed


def _split_h2_sections(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.rstrip().splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if not starts:
        return lines, []

    preamble = lines[: starts[0]]
    sections: list[list[str]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        sections.append(lines[start:end])
    return preamble, sections


def _join_h2_sections(preamble: list[str], sections: list[list[str]]) -> str:
    parts: list[str] = []
    preamble_text = "\n".join(preamble).rstrip()
    if preamble_text:
        parts.append(preamble_text)
    parts.extend("\n".join(section).strip() for section in sections)
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def _plan_h2_archive(text: str, budget: int):
    preamble, sections = _split_h2_sections(text)
    if len(sections) < 2:
        return None

    for keep_count in range(len(sections) - 1, 0, -1):
        kept = sections[:keep_count]
        archived = sections[keep_count:]
        compacted = _join_h2_sections(preamble, kept)
        projected = estimate_tokens(compacted)
        if projected <= budget:
            return {
                "compacted": compacted,
                "archived": archived,
                "kept": kept,
                "projected": projected,
            }
    return None


def _archive_target_path(memory_dir: Path, target: str) -> Path:
    stem = target[:-3].replace("/", "-")
    return memory_dir / "archive" / f"{stem}-{today()}.md"


def _write_archive_entries(memory_dir: Path, target: str, archived_sections: list[list[str]]) -> None:
    readme = memory_dir / "archive" / "README.md"
    if not readme.exists():
        write_text(readme, render_template("archive/README.md", today()))

    archive_path = _archive_target_path(memory_dir, target)
    body = (
        f"## {today()} - From {target}\n"
        "Reason:\n"
        "Active memory exceeded its context budget; older complete entries were moved to explicit-only archive.\n\n"
        + "\n\n".join("\n".join(section).strip() for section in archived_sections)
    )
    if archive_path.exists():
        append_text(archive_path, body)
    else:
        write_text(archive_path, f"# Archived Memory: {target}\n\n{body}\n")


def _run_target_compaction(args, memory_dir: Path) -> int:
    target, path = _target_path(memory_dir, args.target)
    if not path.exists():
        print(f"Target not found: {path}")
        return 1

    budget = budget_for(target)
    original = path.read_text(encoding="utf-8")
    tokens = estimate_tokens(original)

    print("# Target Compaction Plan")
    print(f"Target: {target}")
    print(f"Current tokens: {tokens}/{budget} max")
    if tokens <= budget:
        print("Status: OK")
        return 0

    working = original
    applied_actions: list[str] = []
    if target in BULLET_DEDUPE_TARGETS:
        deduped, removed = _dedupe_bullets(working)
        if removed:
            working = deduped
            projected = estimate_tokens(working)
            print(f"Action: remove {removed} exact duplicate bullet(s)")
            print(f"Projected tokens after dedupe: {projected}/{budget} max")
            if args.apply:
                write_text(path, working)
                append_changelog(memory_dir, f"Compacted {target}: removed {removed} duplicate bullet(s).")
                applied_actions.append("deduped bullets")
            if projected <= budget:
                if args.apply:
                    print("Applied target compaction.")
                else:
                    print("Dry run only. Re-run with --apply to write deterministic changes.")
                return 0

    manual_reason = MANUAL_TARGET_REASONS.get(target)
    if manual_reason:
        print(f"Manual review required: {manual_reason}")
        if applied_actions:
            print("Applied partial deterministic compaction; target remains over budget.")
        elif not args.apply:
            print("Dry run only. No deterministic safe rewrite is available for this target.")
        return 0

    if target in ARCHIVABLE_H2_TARGETS:
        plan = _plan_h2_archive(working, budget)
        if plan is not None:
            archive_path = _archive_target_path(memory_dir, target).relative_to(memory_dir).as_posix()
            print("Action: archive oldest complete H2 entries")
            print(f"Keep entries: {len(plan['kept'])}")
            print(f"Archive entries: {len(plan['archived'])}")
            print(f"Archive path: {archive_path}")
            print(f"Projected tokens: {plan['projected']}/{budget} max")
            if not args.apply:
                print("Dry run only. Re-run with --apply after reviewing the plan.")
                return 0

            write_text(path, plan["compacted"])
            _write_archive_entries(memory_dir, target, plan["archived"])
            if target != "changelog.md":
                append_changelog(memory_dir, f"Compacted {target}: archived {len(plan['archived'])} old entries.")
            print("Applied target compaction.")
            return 0

    if applied_actions:
        print("Applied partial deterministic compaction; target remains over budget.")
    else:
        print("Manual review required: shorten, merge, split into optional modules, or archive content after semantic review.")
        if not args.apply:
            print("Dry run only. No deterministic safe rewrite is available for this target.")
    return 0


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if args.target:
        return _run_target_compaction(args, memory_dir)

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
        prepend_target = target in {"decisions.md", "do-not-use.md"}
        ordered_values = reversed(values) if prepend_target else values
        for item in ordered_values:
            if prepend_target:
                prepend_text(memory_dir / target, _format_for(target, item))
            else:
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
