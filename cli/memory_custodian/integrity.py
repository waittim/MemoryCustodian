"""Pure cross-unit project integrity validation shared by CLI consumers."""

from __future__ import annotations

from pathlib import Path

from .conflicts import ConflictStatus, analyze_conflicts
from .entries import (
    memory_entry_ids,
    parse_structured_entries,
    structured_relation_issues,
)
from .local_overlay import LocalStatus, inspect_overlay
from .protocol import managed_markdown_files, optional_index_paths, read_managed_text
from .subjects import load_subjects, validate_subject_registry


def cross_unit_integrity_findings(
    project_root: Path,
    memory_dir: Path,
    manifest: str,
    *,
    project_id: str | None = None,
    allow_missing_subjects: bool = False,
) -> tuple[list[str], list[str]]:
    """Validate relationships, registry, optional topology, and local binding."""

    issues = validate_subject_registry(memory_dir, project_root)
    if allow_missing_subjects and not (memory_dir / "subjects.md").exists():
        issues = [
            issue for issue in issues
            if issue != "subjects.md: missing managed Subject registry"
        ]
    warnings: list[str] = []
    relation_entries = []
    managed_paths = managed_markdown_files(memory_dir)
    for path in managed_paths:
        relative = path.relative_to(memory_dir).as_posix()
        if relative in {"manifest.md", "subjects.md", "reconciliations.md"} or path.name.casefold() == "readme.md":
            continue
        relation_entries.extend(parse_structured_entries(
            path, read_managed_text(memory_dir, path)
        ))
    issues.extend(
        structured_relation_issues(
            relation_entries,
            merged_subject_ids={
                subject.subject_id
                for subject in load_subjects(memory_dir)
                if subject.status == "merged"
            },
        )
    )

    # Pre-0.7 migration input may legitimately lack Subject/Facet owner
    # metadata. Its renderer preserves those units as legacy memory.
    if not allow_missing_subjects:
        conflict_result = analyze_conflicts(memory_dir)
        for finding in conflict_result.findings:
            message = f"{finding.code}: {finding.message}"
            if finding.status in {ConflictStatus.INVALID, ConflictStatus.CONFLICT}:
                issues.append(message)
            elif finding.status == ConflictStatus.REVIEW:
                warnings.append(message)

    indexed_optional_paths = optional_index_paths(manifest)
    for folder in ("rules", "profiles", "areas"):
        directory = memory_dir / folder
        folder_paths = [
            path for path in managed_paths
            if path.relative_to(memory_dir).as_posix().startswith(folder + "/")
            and path.name.casefold() != "readme.md"
        ]
        if directory.exists() and folder + "/" not in manifest:
            issues.append(
                f"manifest.md: {folder}/ exists but manifest does not describe when to load it"
            )
        for path in folder_paths:
            relative = path.relative_to(memory_dir).as_posix()
            if relative not in indexed_optional_paths:
                issues.append(
                    f"manifest.md: {relative} exists but is missing from optional module index"
                )

    if project_id:
        overlay = inspect_overlay(
            project_root, project_id, shared_ids=memory_entry_ids(memory_dir),
        )
        if overlay.status == LocalStatus.REVIEW:
            target = issues if overlay.corrupt else warnings
            target.extend(f"local overlay: {warning}" for warning in overlay.warnings)
    return issues, warnings
