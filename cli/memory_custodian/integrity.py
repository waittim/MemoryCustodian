"""Pure cross-unit project integrity validation shared by CLI consumers."""

from __future__ import annotations

from pathlib import Path

from .conflicts import ConflictStatus, analyze_snapshot
from .local_overlay import LocalOverlay, LocalStatus, inspect_overlay
from .protocol import optional_index_paths
from .snapshot import MemorySnapshot, build_snapshot


def cross_unit_integrity_findings(
    project_root: Path,
    memory_dir: Path,
    manifest: str,
    *,
    project_id: str | None = None,
    allow_missing_subjects: bool = False,
    snapshot: MemorySnapshot | None = None,
    overlay: LocalOverlay | None = None,
) -> tuple[list[str], list[str]]:
    """Validate one shared snapshot's cross-file integrity and topology."""

    if snapshot is None:
        snapshot = build_snapshot(memory_dir, project_root)
    else:
        # With a supplied capture, its manifest is authoritative.  Standalone
        # callers may still pass a planned manifest that intentionally differs
        # from the current on-disk text.
        manifest = snapshot.manifest_text
    subject_issues = list(snapshot.subject_issues)
    if allow_missing_subjects and snapshot.file_for("subjects.md") is None:
        subject_issues = [
            issue for issue in subject_issues
            if issue != "subjects.md: missing managed Subject registry"
        ]
    issues = [
        f"{getattr(issue, 'conflict_code', None)}: {issue}"
        if getattr(issue, "conflict_code", None)
        else issue
        for issue in subject_issues
    ]
    warnings: list[str] = []
    # Integrity covers every managed formal Entry, including entries in an
    # optional file that has not yet been declared in the manifest.  The
    # complete parsed inventory is already part of the snapshot; do not walk
    # and parse the files a second time here.
    issues.extend(snapshot.integrity_relation_issues)

    # Pre-0.7 migration input may legitimately lack Subject/Facet owner
    # metadata. Its renderer preserves those units as legacy memory.
    if not allow_missing_subjects:
        conflict_result = analyze_snapshot(snapshot)
        for finding in conflict_result.findings:
            # Subject, Entry-schema, and Entry-relation findings are already
            # represented by the snapshot's dedicated diagnostics above (or
            # by the caller's per-file schema pass).  Keep only the
            # cross-unit conflict/review findings here; this prevents the old
            # relation-then-conflict double pipeline and duplicate messages.
            if finding.origin in {"subject-registry", "entry-schema", "entry-relation"}:
                continue
            message = f"{finding.code}: {finding.message}"
            if finding.status in {ConflictStatus.INVALID, ConflictStatus.CONFLICT}:
                issues.append(message)
            elif finding.status == ConflictStatus.REVIEW:
                warnings.append(message)

    indexed_optional_paths = optional_index_paths(manifest)
    for folder in ("rules", "profiles", "areas"):
        folder_paths = [
            item.path for item in snapshot.files
            if item.relative.startswith(folder + "/")
            and item.path.name.casefold() != "readme.md"
        ]
        # ``snapshot.files`` is the captured managed inventory.  An empty
        # optional directory has no managed input to inspect and therefore
        # cannot affect this integrity result.
        folder_present = (
            snapshot.memory_dir / folder in snapshot.managed_directories
            or any(
                item.relative.startswith(folder + "/")
                for item in snapshot.files
            )
        )
        if folder_present and folder + "/" not in manifest:
            issues.append(
                f"manifest.md: {folder}/ exists but manifest does not describe when to load it"
            )
        for path in folder_paths:
            relative = path.relative_to(snapshot.memory_dir).as_posix()
            if relative not in indexed_optional_paths:
                issues.append(
                    f"manifest.md: {relative} exists but is missing from optional module index"
                )

    if overlay is None and project_id:
        overlay = inspect_overlay(
            project_root,
            project_id,
            shared_ids={entry.entry_id for entry in snapshot.relation_entries},
        )
    if overlay is not None and overlay.status == LocalStatus.REVIEW:
        target = issues if overlay.corrupt else warnings
        target.extend(f"local overlay: {warning}" for warning in overlay.warnings)
    return issues, warnings
