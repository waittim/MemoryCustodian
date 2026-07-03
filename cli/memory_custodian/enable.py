"""Enable optional MemoryCustodian modules."""

from __future__ import annotations

from pathlib import Path

from .protocol import (
    append_changelog,
    is_indexable_optional_path,
    is_safe_memory_name,
    manifest_with_optional_module_index,
    resolve_memory_dir,
    resolve_project_root,
    today,
    write_text,
)
from .templates import render_area_template, render_profile_template, render_rule_template, render_template


def _feature_path_and_text(feature: str, current_date: str) -> tuple[str, str] | None:
    if feature == "preferences":
        return "preferences.md", render_template("preferences.md", current_date)
    if feature == "changelog":
        return "changelog.md", render_template("changelog.md", current_date)
    if feature == "rules":
        return "rules/README.md", render_template("rules/README.md", current_date)
    if feature == "profiles":
        return "profiles/README.md", render_template("profiles/README.md", current_date)
    if feature == "archive":
        return "archive/README.md", render_template("archive/README.md", current_date)
    if feature.startswith("rules/"):
        name = feature.removeprefix("rules/")
        if not is_safe_memory_name(name):
            return None
        return f"rules/{name}.md", render_rule_template(name, current_date)
    if feature.startswith("profile/"):
        name = feature.removeprefix("profile/")
        if not is_safe_memory_name(name):
            return None
        return f"profiles/{name}.md", render_profile_template(name, current_date)
    if feature.startswith("profiles/"):
        name = feature.removeprefix("profiles/")
        if not is_safe_memory_name(name):
            return None
        return f"profiles/{name}.md", render_profile_template(name, current_date)
    if feature.startswith("area/"):
        name = feature.removeprefix("area/")
        if not is_safe_memory_name(name):
            return None
        return f"areas/{name}.md", render_area_template(name, current_date)
    if feature.startswith("areas/"):
        name = feature.removeprefix("areas/")
        if not is_safe_memory_name(name):
            return None
        return f"areas/{name}.md", render_area_template(name, current_date)
    return None


def _write_optional(path: Path, text: str, force: bool) -> str:
    if path.exists() and not force:
        return "kept"
    write_text(path, text)
    return "written"


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        return 1

    result = _feature_path_and_text(args.feature, today())
    if result is None:
        print(f"Unknown or invalid optional feature: {args.feature}")
        return 1

    relative_path, text = result
    state = _write_optional(memory_dir / relative_path, text, args.force)
    manifest_state = None
    manifest_path = memory_dir / "manifest.md"
    if is_indexable_optional_path(relative_path) and manifest_path.exists():
        updated_manifest, changed = manifest_with_optional_module_index(manifest_path.read_text(encoding="utf-8"), relative_path)
        if changed:
            write_text(manifest_path, updated_manifest)
            manifest_state = f"indexed {relative_path}"
    append_changelog(memory_dir, f"Enabled optional memory module {relative_path}.")
    print(f"{relative_path}: {state}")
    if manifest_state:
        print(f"manifest.md: {manifest_state}")
    return 0
