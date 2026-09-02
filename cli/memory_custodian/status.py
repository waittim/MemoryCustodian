"""Report MemoryCustodian health."""

from __future__ import annotations

from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    budget_for,
    budget_state,
    compare_versions,
    count_h2_entries,
    count_inbox_items,
    estimate_tokens,
    long_decision_entries,
    resolve_memory_dir,
    resolve_project_root,
)
from . import __version__
from .templates import CORE_FILES, brief_needs_curation
from .snapshot import build_snapshot


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)

    print("MemoryCustodian status")
    print(f"CLI version: {__version__}")
    print(f"Memory directory: {memory_dir}")
    if not memory_dir.exists():
        print("Status: MISSING")
        return 1
    # Capture managed inventory, source text, parser results, and manifest
    # contract once.  Status is intentionally a pure consumer of this view;
    # later metadata, budget, and optional-module reporting must not observe a
    # second manifest or inventory revision.
    snapshot = build_snapshot(memory_dir, project_root)
    files_by_relative = {item.relative: item for item in snapshot.files}

    exit_code = 0
    metadata = snapshot.manifest_contract.as_dict()
    # A missing manifest is already reported as a missing core file below;
    # preserve the historical "Protocol version: missing" line instead of
    # turning that absence into a duplicate metadata error.
    protocol_error = (
        snapshot.manifest_contract.error
        if snapshot.manifest_contract.present
        else None
    )
    if protocol_error:
        exit_code = 1
    protocol_version = metadata.get("protocol_version")
    if protocol_error:
        if snapshot.manifest_contract.migration_available:
            print(
                "Protocol version: 0.7 / entry schema 1 "
                "(migration available to entry schema 2)"
            )
        else:
            print(f"Protocol metadata: INVALID ({protocol_error})")
    elif protocol_version:
        comparison = compare_versions(protocol_version, CURRENT_PROTOCOL_VERSION)
        if comparison == 0:
            print(f"Protocol version: {protocol_version} (current)")
        elif comparison is not None and comparison < 0:
            print(f"Protocol version: {protocol_version} (migration available to {CURRENT_PROTOCOL_VERSION})")
        elif comparison is not None and comparison > 0:
            print(f"Protocol version: {protocol_version} (newer than CLI supports {CURRENT_PROTOCOL_VERSION})")
            exit_code = 1
        else:
            print(f"Protocol version: {protocol_version} (invalid)")
            exit_code = 1
    else:
        print(f"Protocol version: missing (migration available to {CURRENT_PROTOCOL_VERSION})")

    for name in CORE_FILES:
        source = files_by_relative.get(name)
        if source is None:
            print(f"{name}: MISSING")
            exit_code = 1
            continue
        text = source.text
        tokens = estimate_tokens(text)
        budget = budget_for(name)
        usage_state = budget_state(tokens, budget) if budget is not None else "OK"
        long_entries = long_decision_entries(text) if name == "decisions.md" else []
        if name == "manifest.md" and protocol_error:
            state = "INVALID"
        elif name == "brief.md" and brief_needs_curation(text):
            state = "NEEDS CURATION"
        elif usage_state != "OK":
            state = usage_state
        elif long_entries:
            state = "LONG ENTRIES"
        else:
            state = "OK"
        detail = f", {tokens} tokens"
        if budget is not None:
            detail += f"/{budget} max"
        if state == "OVER BUDGET":
            detail += f", run compact --target {name}"
        elif state == "NEAR LIMIT":
            detail += f", maintenance recommended before next write; run compact --target {name}"
        elif state == "NEEDS CURATION":
            detail += ", replace generated placeholders with real project context"
        elif state == "LONG ENTRIES":
            detail += f", shorten {len(long_entries)} decision(s) over {DECISION_ENTRY_BUDGET} tokens"
        if name == "inbox.md":
            detail += f", {count_inbox_items(text)} items"
            if count_inbox_items(text) > 30:
                detail += ", compaction recommended"
        if name in {"decisions.md", "do-not-use.md"}:
            detail += f", {count_h2_entries(text)} entries"
        if name == "decisions.md" and long_entries and state != "LONG ENTRIES":
            detail += f", {len(long_entries)} decision(s) over {DECISION_ENTRY_BUDGET}-token entry guide"
        print(f"{name}: {state}{detail}")
        if state != "OK":
            exit_code = 1
    for name in ("preferences.md", "changelog.md"):
        source = files_by_relative.get(name)
        if source is None:
            print(f"{name}: not enabled")
            continue
        text = source.text
        tokens = estimate_tokens(text)
        budget = budget_for(name)
        state = "OK" if budget is None else budget_state(tokens, budget)
        detail = f", {tokens} tokens"
        if budget is not None:
            detail += f"/{budget} max"
        if state in {"NEAR LIMIT", "OVER BUDGET"}:
            detail += f", run compact --target {name}"
        print(f"{name}: {state}{detail}")
        if state != "OK":
            exit_code = 1
    for folder in ("rules", "profiles", "areas", "archive"):
        folder_files = [
            item for item in snapshot.files
            if item.relative.startswith(folder + "/")
        ]
        if not folder_files and snapshot.memory_dir / folder not in snapshot.managed_directories:
            print(f"{folder}/: not enabled")
            continue
        files = sorted(
            item.relative.removeprefix(folder + "/")
            for item in folder_files
            if item.relative.count("/") == 1
        )
        if files:
            print(f"{folder}/: enabled, {len(files)} markdown file(s)")
        else:
            print(f"{folder}/: enabled, empty")
    return exit_code
