"""Migrate project memory files to the current MemoryCustodian protocol."""

from __future__ import annotations

from .protocol import (
    append_changelog,
    manifest_with_current_protocol_metadata,
    manifest_with_current_task_routing,
    manifest_with_optional_index,
    resolve_memory_dir,
    resolve_project_root,
    write_text,
)


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest_path = memory_dir / "manifest.md"
    if not memory_dir.exists():
        print(f"Memory directory missing: {memory_dir}")
        return 1
    if not manifest_path.exists():
        print(f"manifest.md missing: {manifest_path}")
        return 1

    original = manifest_path.read_text(encoding="utf-8")
    updated, metadata_changed = manifest_with_current_protocol_metadata(original)
    updated, routing_changed = manifest_with_current_task_routing(updated)
    updated, index_changed = manifest_with_optional_index(updated)
    changes: list[str] = []
    if metadata_changed:
        changes.append("manifest.md: add/update MemoryCustodian Protocol metadata")
    if routing_changed:
        changes.append("manifest.md: load decisions.md for implementation, execution, and debugging")
    if index_changed:
        changes.append("manifest.md: add/update optional module index")

    if not changes:
        print("MemoryCustodian migrate: no changes needed")
        return 0

    print("MemoryCustodian migrate plan:")
    for change in changes:
        print(f"- {change}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to write migration changes.")
        return 0

    write_text(manifest_path, updated)
    append_changelog(memory_dir, "Migrated memory manifest to the current MemoryCustodian protocol.")
    print("Applied migration.")
    return 0
