"""Report MemoryCustodian health."""

from __future__ import annotations

from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    budget_for,
    compare_versions,
    count_h2_entries,
    count_inbox_items,
    estimate_tokens,
    long_decision_entries,
    protocol_metadata,
    resolve_memory_dir,
    resolve_project_root,
)
from . import __version__
from .templates import CORE_FILES, brief_needs_curation


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)

    print("MemoryCustodian status")
    print(f"CLI version: {__version__}")
    print(f"Memory directory: {memory_dir}")
    if not memory_dir.exists():
        print("Status: MISSING")
        return 1

    exit_code = 0
    manifest_path = memory_dir / "manifest.md"
    manifest = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else ""
    metadata = protocol_metadata(manifest)
    protocol_version = metadata.get("protocol_version")
    if protocol_version:
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
        path = memory_dir / name
        if not path.exists():
            print(f"{name}: MISSING")
            exit_code = 1
            continue
        text = path.read_text(encoding="utf-8")
        tokens = estimate_tokens(text)
        budget = budget_for(name)
        long_entries = long_decision_entries(text) if name == "decisions.md" else []
        if name == "brief.md" and brief_needs_curation(text):
            state = "NEEDS CURATION"
        elif budget is not None and tokens > budget:
            state = "OVER BUDGET"
        elif long_entries:
            state = "LONG ENTRIES"
        else:
            state = "OK"
        detail = f", {tokens} tokens"
        if budget is not None:
            detail += f"/{budget} max"
        if state == "OVER BUDGET":
            detail += f", run compact --target {name}"
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
        path = memory_dir / name
        if not path.exists():
            print(f"{name}: not enabled")
            continue
        text = path.read_text(encoding="utf-8")
        tokens = estimate_tokens(text)
        budget = budget_for(name)
        state = "OK" if budget is None or tokens <= budget else "OVER BUDGET"
        detail = f", {tokens} tokens"
        if budget is not None:
            detail += f"/{budget} max"
        if state != "OK":
            detail += f", run compact --target {name}"
        print(f"{name}: {state}{detail}")
        if state != "OK":
            exit_code = 1
    for folder in ("rules", "profiles", "areas", "archive"):
        directory = memory_dir / folder
        if not directory.exists():
            print(f"{folder}/: not enabled")
            continue
        files = sorted(path.name for path in directory.glob("*.md"))
        if files:
            print(f"{folder}/: enabled, {len(files)} markdown file(s)")
        else:
            print(f"{folder}/: enabled, empty")
    return exit_code
