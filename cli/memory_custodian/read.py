"""Render a small MemoryCustodian context pack."""

from __future__ import annotations

from .protocol import budget_for, is_safe_memory_name, resolve_memory_dir, resolve_project_root, task_file_specs, trim_to_budget


def _optional_requested(kind: str, names: list[str]) -> list[tuple[str, bool]]:
    files: list[tuple[str, bool]] = []
    for name in names:
        if not is_safe_memory_name(name):
            continue
        files.append((f"{kind}/{name}.md", False))
    return files


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    files = task_file_specs(args.task)
    files += _optional_requested("profiles", args.profile)
    files += _optional_requested("areas", args.area)

    loaded: list[str] = []
    missing_required: list[str] = []
    skipped_optional: list[str] = []
    trimmed_files: list[str] = []
    contents: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, required in files:
        if name in seen:
            continue
        seen.add(name)
        path = memory_dir / name
        if path.exists():
            loaded.append(name)
            text, trimmed = trim_to_budget(path.read_text(encoding="utf-8").strip(), budget_for(name))
            if trimmed:
                trimmed_files.append(name)
            contents.append((name, text))
        elif required:
            missing_required.append(name)
        else:
            skipped_optional.append(name)

    print("# Memory Context Pack")
    print(f"Task: {args.task}")
    print("Loaded:")
    for name in loaded:
        print(f"- {name}")
    if missing_required:
        print("Missing required:")
        for name in missing_required:
            print(f"- {name}")
    if skipped_optional:
        print("Skipped optional:")
        for name in skipped_optional:
            print(f"- {name}")
    if trimmed_files:
        print("Trimmed:")
        for name in trimmed_files:
            print(f"- {name}")
    if not args.names_only:
        for name, text in contents:
            print(f"\n## {name}\n")
            print(text)
    return 0 if loaded and not missing_required else 1
