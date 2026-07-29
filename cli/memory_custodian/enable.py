"""Enable optional MemoryCustodian modules."""

from __future__ import annotations

from pathlib import Path

from .locking import bootstrap_lock_id, mutation_lock
from .protocol import (
    changelog_text,
    is_indexable_optional_path,
    is_safe_memory_name,
    manifest_with_optional_module_index,
    project_id_from_manifest,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
from .mutations import TextMutation, apply_mutations
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


def _build_mutations(
    memory_dir: Path,
    manifest_path: Path,
    relative_path: str,
    template_text: str,
) -> tuple[str, str | None, list[TextMutation]]:
    path = memory_dir / relative_path
    state = "kept" if path.exists() else "written"
    target_text = path.read_text(encoding="utf-8") if path.exists() else template_text
    planned: dict[Path, str] = {} if path.exists() else {path: target_text}
    manifest_state = None
    if is_indexable_optional_path(relative_path):
        updated_manifest, changed = manifest_with_optional_module_index(
            manifest_path.read_text(encoding="utf-8"),
            relative_path,
        )
        if changed:
            planned[manifest_path] = updated_manifest
            manifest_state = f"indexed {relative_path}"
    changed_state = bool(planned)
    changelog = memory_dir / "changelog.md"
    if changed_state and relative_path == "changelog.md":
        planned[changelog] = changelog_text(
            target_text,
            f"Enabled optional memory module {relative_path}.",
        )
    elif changed_state and changelog.exists():
        planned[changelog] = changelog_text(
            changelog.read_text(encoding="utf-8"),
            f"Enabled optional memory module {relative_path}.",
        )
    return state, manifest_state, [
        TextMutation(target, content) for target, content in planned.items()
    ]


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory not found: {memory_dir}")
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    if args.force:
        raise ValueError("enable --force was removed because it could overwrite curated memory; existing modules are always preserved")

    result = _feature_path_and_text(args.feature, today())
    if result is None:
        raise ValueError(f"Unknown or invalid optional feature: {args.feature}")

    relative_path, text = result
    manifest_text = manifest_path.read_text(encoding="utf-8")
    project_id = (
        project_id_from_manifest(manifest_text, required=False)
        or bootstrap_lock_id(project_root)
    )
    with mutation_lock(
        project_id,
        project_root,
        "enable",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
    ):
        state, manifest_state, mutations = _build_mutations(
            memory_dir,
            manifest_path,
            relative_path,
            text,
        )
        if mutations:
            apply_mutations(mutations)
    if not mutations:
        print(f"{relative_path}: already enabled")
        return 0
    print(f"{relative_path}: {state}")
    if manifest_state:
        print(f"manifest.md: {manifest_state}")
    return 0
