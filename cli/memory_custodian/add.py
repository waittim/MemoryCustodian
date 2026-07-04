"""Add a memory entry."""

from __future__ import annotations

from pathlib import Path

from .protocol import (
    append_changelog,
    append_text,
    is_indexable_optional_path,
    is_safe_memory_name,
    manifest_with_optional_module_index,
    resolve_memory_dir,
    resolve_project_root,
    today,
    write_text,
)
from .templates import render_area_template, render_profile_template, render_rule_template, render_template

TARGETS = {
    "decision": "decisions.md",
    "constraint": "constraints.md",
    "preference": "preferences.md",
    "tombstone": "do-not-use.md",
    "do-not-use": "do-not-use.md",
    "inbox": "inbox.md",
}


def _title(message: str) -> str:
    clean = " ".join(message.strip().split())
    return clean[:72] if clean else "Untitled memory"


def _entry(kind: str, message: str, reason: str | None) -> str:
    current_date = today()
    if kind == "decision":
        body = f"## {current_date} - {_title(message)}\nDecision:\n{message}"
        if reason:
            body += f"\nReason:\n{reason}"
        return body
    if kind == "constraint":
        return f"- {message}"
    if kind == "preference":
        return f"- {message}"
    if kind in {"rule", "profile", "area"}:
        return f"- {message}"
    if kind in {"tombstone", "do-not-use"}:
        why = reason or "Added as a rejected or guarded topic."
        return (
            f"## Tombstone: {_title(message)}\n"
            f"Do not reintroduce unless the user explicitly reverses this. Reason: {why} Date: {current_date}."
        )
    return f"## {current_date}\n- {message}"


def _ensure_target(path: Path, kind: str, name: str | None) -> None:
    if path.exists():
        return
    current_date = today()
    if kind == "preference":
        write_text(path, render_template("preferences.md", current_date))
    elif kind == "rule" and name:
        write_text(path, render_rule_template(name, current_date))
    elif kind == "profile" and name:
        write_text(path, render_profile_template(name, current_date))
    elif kind == "area" and name:
        write_text(path, render_area_template(name, current_date))


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        return 1

    kind = args.type
    if kind in {"rule", "profile", "area"}:
        if not args.name:
            print(f"--name is required when --type is {kind}")
            return 1
        if not is_safe_memory_name(args.name):
            print(f"Invalid {kind} name: {args.name}")
            return 1
        folder = "rules" if kind == "rule" else f"{kind}s"
        target = f"{folder}/{args.name}.md"
    else:
        target = TARGETS[kind]
    target_path = memory_dir / target
    _ensure_target(target_path, kind, args.name)
    append_text(target_path, _entry(kind, args.message, args.reason))
    manifest_path = memory_dir / "manifest.md"
    indexed = False
    if is_indexable_optional_path(target) and manifest_path.exists():
        updated_manifest, indexed = manifest_with_optional_module_index(manifest_path.read_text(encoding="utf-8"), target)
        if indexed:
            write_text(manifest_path, updated_manifest)
    append_changelog(memory_dir, f"Added {kind} memory to {target}.")
    print(f"Added {kind} memory to {target_path}")
    if indexed:
        print(f"Indexed optional memory in {manifest_path}")
    return 0
