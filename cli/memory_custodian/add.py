"""Add a memory entry."""

from __future__ import annotations

from pathlib import Path

from .protocol import (
    DECISION_ENTRY_BUDGET,
    append_changelog,
    append_text,
    budget_for,
    estimate_tokens,
    is_indexable_optional_path,
    is_safe_memory_name,
    manifest_with_optional_module_index,
    prepend_text,
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

NEWEST_FIRST_TYPES = {"decision", "tombstone", "do-not-use", "inbox"}
AREA_SCOPED_TYPES = {"decision", "constraint", "preference", "tombstone", "do-not-use"}


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


def _ensure_target(path: Path, kind: str, name: str | None, area: str | None = None) -> None:
    if path.exists():
        return
    current_date = today()
    if area:
        write_text(path, render_area_template(area, current_date))
    elif kind == "preference":
        write_text(path, render_template("preferences.md", current_date))
    elif kind == "rule" and name:
        write_text(path, render_rule_template(name, current_date))
    elif kind == "profile" and name:
        write_text(path, render_profile_template(name, current_date))
    elif kind == "area" and name:
        write_text(path, render_area_template(name, current_date))


def _report_budget(path: Path, target: str) -> None:
    budget = budget_for(target)
    if budget is None:
        return
    tokens = estimate_tokens(path.read_text(encoding="utf-8"))
    print(f"Budget: {target} {tokens}/{budget} tokens")
    if tokens > budget:
        print(f"Warning: {target} is over its context budget.")
        if target == "decisions.md":
            print("Next: consolidate or relocate scoped decisions before considering age-based archival.")
        else:
            print(f"Next: review `memory-custodian compact --target {target}`.")
    elif tokens * 5 >= budget * 4:
        print(f"Warning: {target} has reached at least 80% of its context budget.")


def _check_decision_entry_budget(entry: str, allow_long: bool) -> bool:
    tokens = estimate_tokens(entry)
    print(f"Decision entry budget: {tokens}/{DECISION_ENTRY_BUDGET} tokens")
    if tokens > DECISION_ENTRY_BUDGET and not allow_long:
        print(
            "Not added: shorten Decision to one or two sentences and Reason to one sentence; "
            "move supporting detail to constraints, matched area context, or source documentation."
        )
        print("Use --allow-long only when splitting would lose essential decision semantics.")
        return False
    if tokens > DECISION_ENTRY_BUDGET:
        print("Warning: adding an explicitly allowed long decision entry.")
    elif tokens * 5 >= DECISION_ENTRY_BUDGET * 4:
        print("Warning: decision entry has reached at least 80% of its recommended budget.")
    return True


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        return 1

    kind = args.type
    if args.allow_long and kind != "decision":
        print("--allow-long can only be used when --type is decision")
        return 1
    scoped_area = args.area
    if scoped_area:
        if args.name:
            print("--area and --name cannot be used together")
            return 1
        if kind not in AREA_SCOPED_TYPES:
            print(f"--area cannot be used when --type is {kind}")
            return 1
        if not is_safe_memory_name(scoped_area):
            print(f"Invalid area name: {scoped_area}")
            return 1
        target = f"areas/{scoped_area}.md"
    elif kind in {"rule", "profile", "area"}:
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
    entry = _entry(kind, args.message, args.reason)
    if kind == "decision" and not _check_decision_entry_budget(entry, args.allow_long):
        return 1
    target_path = memory_dir / target
    _ensure_target(target_path, kind, args.name, scoped_area)
    if kind in NEWEST_FIRST_TYPES:
        remove_lines = ("No unprocessed memory candidates.",) if kind == "inbox" else ()
        prepend_text(target_path, entry, remove_lines=remove_lines)
    else:
        append_text(target_path, entry)
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
    _report_budget(target_path, target)
    return 0
