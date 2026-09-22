"""Conservative, staged migration to the current Protocol 0.8 contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

from .entries import (
    ENTRY_ID_RE,
    VALID_SCOPES_RE,
    entry_unit_issues,
    heading_entry_ids,
    line_safe_markdown_body,
    migrate_entry_schema,
    memory_entry_ids,
    parse_structured_entries,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    validate_evidence,
    LEGACY_ENTRY_SCHEMA_VERSION,
)
from .locking import (
    discard_private_file,
    project_mutation_guard,
    read_private_file,
    write_private_file,
    private_state_directory,
)
from .markdown import visible_lines
from .mutations import (
    PrivateDeleteMutation,
    PrivateTextMutation,
    TextMutation,
    apply_mutations,
    apply_private_mutations,
    restore_text_file_exact,
)
from .local_overlay import LocalStatus, inspect_overlay, overlay_directory
from .plans import (
    MutationPlan,
    digest_text,
    discard_pending_seed,
    pending_project_id,
    pending_entry_suffixes,
    print_plan,
)
from .transactions import apply_plan_transaction
from .transactions import apply_transaction, bootstrap_binding_id
from .protocol import (
    CURRENT_ENTRY_SCHEMA_VERSION,
    CURRENT_PROTOCOL_VERSION,
    changelog_text,
    compare_versions,
    entry_schema_version_for_manifest,
    manifest_with_complete_task_routing,
    manifest_with_current_protocol_metadata,
    manifest_with_current_task_routing,
    manifest_contract_metadata,
    manifest_with_optional_index,
    manifest_with_protocol_07_optional_routes,
    managed_markdown_files,
    parse_markdown_units,
    protocol_metadata,
    read_managed_text,
    read_no_follow_text,
    strict_protocol_metadata,
    validate_manifest_routes,
    valid_project_id,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
from .routes import parse_optional_module_index
from .templates import render_template
from .snapshot import build_snapshot


@dataclass(frozen=True)
class _MigrationPreimage:
    """One exact shared or private file state captured before migration apply."""

    path: Path
    label: str
    text: str | None
    private: bool


def _capture_migration_preimages(
    memory_dir: Path,
    shared_mutations: tuple[TextMutation, ...],
    private_mutations: tuple[PrivateTextMutation, ...],
) -> tuple[_MigrationPreimage, ...]:
    """Capture every apply operand before any migration write is attempted."""

    preimages: list[_MigrationPreimage] = []
    for mutation in shared_mutations:
        try:
            mutation.path.lstat()
        except FileNotFoundError:
            text = None
        else:
            text = read_managed_text(memory_dir, mutation.path, required=True)
        preimages.append(
            _MigrationPreimage(
                mutation.path,
                mutation.path.relative_to(memory_dir).as_posix(),
                text,
                False,
            )
        )
    for mutation in private_mutations:
        try:
            mutation.path.lstat()
        except FileNotFoundError:
            text = None
        else:
            text = read_private_file(mutation.path)
        preimages.append(
            _MigrationPreimage(
                mutation.path,
                f"local/{mutation.relative}",
                text,
                True,
            )
        )
    return tuple(preimages)


def _restore_migration_preimages(
    preimages: tuple[_MigrationPreimage, ...],
    manifest_path: Path,
) -> tuple[str, ...]:
    """Best-effort restore of all migration operands, with manifest first."""

    # Restore the grammar selector before the other operands.  If an
    # individual recovery write fails, every subsequent attempt still runs,
    # but the manifest is never intentionally left at schema 2 while a local
    # or shared operand is still at schema 1.
    ordered = sorted(
        preimages,
        key=lambda item: (
            item.path != manifest_path or item.private,
            item.label,
        ),
    )
    failures: list[str] = []
    for preimage in ordered:
        try:
            if preimage.private:
                if preimage.text is None:
                    discard_private_file(preimage.path)
                else:
                    write_private_file(preimage.path, preimage.text)
            else:
                restore_text_file_exact(preimage.path, preimage.text)
        except Exception as exc:
            failures.append(f"{preimage.label}: {exc}")
    return tuple(failures)


def _legacy_key(relative: str, section: str, index: int) -> str:
    return hashlib.sha256(f"{relative}\0{index}\0{section}".encode("utf-8")).hexdigest()


def _legacy_id(relative: str, section: str, index: int, code: str, suffixes: dict[str, str]) -> str:
    suffix = suffixes[_legacy_key(relative, section, index)]
    date_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", section.splitlines()[0])
    stamp = "".join(date_match.groups()) if date_match else "19700101"
    return f"MC-{code}-{stamp}-{suffix}"


def _migrate_decisions(
    text: str,
    suffixes: dict[str, str],
    relative: str = "decisions.md",
    *,
    scope: str = "project",
    code: str = "DEC",
    used_ids: set[str] | None = None,
) -> tuple[str, int, int, tuple[str, ...]]:
    occupied_ids = used_ids if used_ids is not None else set()
    document = parse_markdown_units(text)
    changed = 0
    manual = 0
    replacements: list[tuple[int, int, int, str]] = []
    generated_ids: list[str] = []
    for index, unit in enumerate(document.units):
        if unit.kind != "h2":
            continue
        section = unit.text
        if ENTRY_ID_RE.search(section.splitlines()[0]):
            continue
        visible = {line.index: line.text for line in visible_lines(section)}
        if not any(line.strip() == "Decision:" for line in visible.values()):
            manual += 1
            continue
        entry_id = _legacy_id(relative, section, index, code, suffixes)
        if entry_id.casefold() in occupied_ids:
            manual += 1
            continue
        lines = section.splitlines()
        title = re.sub(r"^##\s+(?:\d{4}-\d{2}-\d{2}\s+-\s+)?", "", lines[0]).strip()

        # Protect each legacy body *range* as one value.  Calling
        # ``line_safe_markdown_body`` for every line creates adjacent
        # ``memory-custodian-body-v1`` wrappers; the shared Entry parser can
        # only recognize a wrapper at the start of an empty body occurrence,
        # so later wrappers would become literal body text or new fields.
        # Decision/Reason are the only legacy field boundaries we preserve;
        # everything between them is one semantic body, including protocol-
        # shaped lines, blank lines, and trailing spaces.
        safe_body: list[str] = []
        body_start: int | None = None

        def append_body(end: int) -> None:
            nonlocal body_start
            if body_start is not None:
                body = "\n".join(lines[body_start:end])
                if body:
                    safe_body.append(line_safe_markdown_body(body))
                else:
                    safe_body.extend(lines[body_start:end])
            body_start = None

        for line_index, line in enumerate(lines[1:], start=1):
            is_boundary = (
                line_index in visible
                and not line.startswith((" ", "\t"))
                and line.rstrip(" \t") in {"Decision:", "Reason:"}
            )
            if is_boundary:
                append_body(line_index)
                safe_body.append(line)
                body_start = line_index + 1
            elif body_start is None:
                # Preserve source before the first legacy body marker.  The
                # existing structural validation will decide whether such a
                # preamble is a safe migrated Entry.
                safe_body.append(line)
        append_body(len(lines))
        migrated = "\n".join(
            [
                f"## {entry_id} — {title}",
                "",
                "Status: active",
                f"Scope: {scope}",
                "Evidence:",
                "- legacy-unverified",
                "",
                *safe_body,
            ]
        )
        parsed = parse_structured_entries(
            Path(relative),
            migrated,
            entry_schema_version=CURRENT_ENTRY_SCHEMA_VERSION,
        )
        if len(parsed) != 1 or parsed[0].entry_id.casefold() != entry_id.casefold():
            manual += 1
            continue
        validation_issues = [
            *structured_entry_schema_issues(parsed[0], relative),
            *structured_entry_storage_issues(parsed[0], relative),
        ]
        if validation_issues:
            manual += 1
            continue
        generated_ids.append(entry_id)
        occupied_ids.add(entry_id.casefold())
        replacements.append((unit.start_line, unit.end_line, len(section.splitlines()), migrated))
        changed += 1
    rendered = text
    if replacements:
        source_lines = text.splitlines(keepends=True)
        for start, end, old_line_count, replacement in sorted(replacements, reverse=True):
            if start < 0 or end > len(source_lines) or start + old_line_count > end:
                raise ValueError("Migration source changed while building an exact-range mutation.")
            trailing = source_lines[start + old_line_count:end]
            eol = "\r\n" if any(line.endswith("\r\n") for line in source_lines[start:end]) else "\n"
            replacement_lines = [line + eol for line in replacement.splitlines()]
            source_lines[start:end] = [*replacement_lines, *trailing]
        rendered = "".join(source_lines)
    return (
        rendered,
        changed,
        manual,
        tuple(generated_ids),
    )


def _migration_entry_seed(
    project_root: Path,
    manifest: str,
    sources: dict[str, str],
) -> tuple[dict[str, str], Path | None]:
    keys: list[str] = []
    fingerprint_parts = [digest_text(manifest)]
    for relative, text in sorted(sources.items()):
        fingerprint_parts.extend([relative, digest_text(text)])
        for index, unit in enumerate(parse_markdown_units(text).units):
            if unit.kind != "h2":
                continue
            section = unit.text
            if (
                not ENTRY_ID_RE.search(section.splitlines()[0])
                and any(
                    line.text.strip() == "Decision:"
                    for line in visible_lines(section)
                )
            ):
                keys.append(_legacy_key(relative, section, index))
    source_sha = digest_text("\0".join(fingerprint_parts))
    return pending_entry_suffixes("migrate-entries", project_root, source_sha, keys)


def _migration_sources(memory_dir: Path, manifest: str) -> dict[str, str]:
    """Read every migration operand before creating persistent preview seeds."""

    relatives = {"decisions.md"}
    relatives.update(
        declaration.module_id
        for declaration in parse_optional_module_index(
            manifest,
            legacy_compatible=True,
        )
        if declaration.module_type == "areas"
    )
    sources: dict[str, str] = {}
    resolved_memory = memory_dir.resolve()
    for relative in sorted(relatives):
        path = memory_dir.joinpath(*Path(relative).parts)
        if path.is_symlink():
            # Resolve escaping symlinks before rejecting operand type so
            # out-of-tree targets report the escape error. Use strict resolve
            # so Python 3.13+ self-referential loops fail closed instead of
            # returning the symlink path.
            try:
                resolved_path = path.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ValueError(
                    f"Migration operand must be a regular non-symlink file: {relative}"
                ) from exc
            try:
                resolved_path.relative_to(resolved_memory)
            except ValueError as exc:
                raise ValueError(
                    f"Migration operand escapes the managed memory directory: {relative}"
                ) from exc
            raise ValueError(
                f"Migration operand must be a regular non-symlink file: {relative}"
            )
        if path.exists():
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"Migration operand must be a regular non-symlink file: {relative}"
                )
        try:
            resolved_path = path.resolve(strict=path.exists())
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                f"Migration operand cannot be safely resolved: {relative}"
            ) from exc
        try:
            resolved_path.relative_to(resolved_memory)
        except ValueError as exc:
            raise ValueError(
                f"Migration operand escapes the managed memory directory: {relative}"
            ) from exc
        if path.exists():
            sources[relative] = read_managed_text(memory_dir, path)
    return sources


def _entry_schema_sources(memory_dir: Path) -> dict[str, str]:
    """Capture every managed Entry-bearing source for schema migration."""

    sources: dict[str, str] = {}
    for path in managed_markdown_files(memory_dir):
        relative = path.relative_to(memory_dir).as_posix()
        if relative in {"manifest.md", "subjects.md", "reconciliations.md"}:
            continue
        if path.name.casefold() == "readme.md":
            continue
        sources[relative] = read_managed_text(memory_dir, path)
    return sources


def _local_schema_migrations(
    project_root: Path,
    memory_dir: Path,
    project_id: str | None,
    *,
    entry_schema_version: str,
) -> tuple[tuple[PrivateTextMutation, ...], int, tuple[str, ...]]:
    """Capture bound local Entries before the shared manifest flips grammar.

    Local state is repo-external, but its Entry grammar is selected by the
    shared manifest.  A bound schema-1 overlay therefore has to migrate in
    the same confirmed operation; otherwise changing the shared manifest to
    schema 2 would make the next read strip a literal body wrapper.  Unsafe,
    unbound, or multi-root overlays are blocked rather than guessed at.
    """

    if (
        not project_id
        or entry_schema_version == CURRENT_ENTRY_SCHEMA_VERSION
    ):
        return (), 0, ()
    try:
        overlay = inspect_overlay(
            project_root,
            project_id,
            shared_ids=set(memory_entry_ids(memory_dir)),
            entry_schema_version=entry_schema_version,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return (), 0, (f"Local overlay could not be inspected safely: {exc}",)
    if overlay.status == LocalStatus.DISABLED:
        return (), 0, ()
    if overlay.status != LocalStatus.BOUND:
        detail = "; ".join(overlay.warnings) or overlay.status.value
        return (
            (),
            0,
            (
                "Local overlay must be bound and free of review warnings before "
                f"Entry schema migration ({detail}).",
            ),
        )
    migrations: list[PrivateTextMutation] = []
    changed = 0
    for captured in overlay.captured_modules:
        migrated, count = migrate_entry_schema(
            captured.path,
            captured.text,
            from_schema=entry_schema_version,
            to_schema=CURRENT_ENTRY_SCHEMA_VERSION,
        )
        if count:
            migrations.append(PrivateTextMutation(captured.path, captured.relative, migrated))
            changed += count
    return tuple(migrations), changed, ()


def _validate_existing_formal_entries(
    project_root: Path,
    memory_dir: Path,
    *,
    entry_schema_version: str = LEGACY_ENTRY_SCHEMA_VERSION,
) -> None:
    """Reject formal Entries that an upgrade would otherwise grandfather as 0.7."""

    issues: list[str] = []
    id_counts: dict[str, int] = {}
    for path in managed_markdown_files(memory_dir):
        relative = path.relative_to(memory_dir).as_posix()
        if path.name.casefold() == "readme.md":
            continue
        text = read_managed_text(memory_dir, path)
        issues.extend(entry_unit_issues(text, relative))
        for entry_id in heading_entry_ids(text):
            key = entry_id.casefold()
            id_counts[key] = id_counts.get(key, 0) + 1
        for entry in parse_structured_entries(
            path,
            text,
            entry_schema_version=entry_schema_version,
        ):
            issues.extend(structured_entry_schema_issues(entry, relative))
            issues.extend(structured_entry_storage_issues(entry, relative))
            if entry.status not in {"active", "candidate", "superseded", "promoted"}:
                issues.append(
                    f"{relative}: {entry.entry_id} has invalid Status {entry.status!r}"
                )
            if not VALID_SCOPES_RE.fullmatch(entry.scope):
                issues.append(
                    f"{relative}: {entry.entry_id} has invalid Scope {entry.scope!r}"
                )
            if entry.evidence:
                try:
                    validate_evidence(
                        entry.evidence,
                        project_root,
                        candidate=entry.status in {"candidate", "promoted"},
                        allow_missing=True,
                        allow_internal=entry.status not in {"candidate", "promoted"},
                    )
                except ValueError:
                    issues.append(
                        f"{relative}: {entry.entry_id} has invalid Evidence schema or unsafe source path"
                    )
    duplicates = sorted(key for key, count in id_counts.items() if count != 1)
    issues.extend(f"duplicate Entry ID: {entry_id}" for entry_id in duplicates)
    if issues:
        preview = "; ".join(issues[:5])
        suffix = f"; and {len(issues) - 5} more" if len(issues) > 5 else ""
        raise ValueError(
            "Migration requires manual repair of existing formal Entries before upgrade: "
            + preview
            + suffix
        )


def _upgraded_manifest(
    original: str,
    project_id: str,
) -> tuple[str, bool, bool, bool, int]:
    """Build and validate the complete migration candidate without local state."""

    routed, optional_routes_changed, legacy_optional_count = (
        manifest_with_protocol_07_optional_routes(original)
    )
    updated, metadata_changed = manifest_with_current_protocol_metadata(
        routed,
        project_id=project_id,
    )
    updated, routing_changed = manifest_with_current_task_routing(updated)
    updated, missing_routes_changed = manifest_with_complete_task_routing(updated)
    routing_changed = routing_changed or missing_routes_changed
    updated, index_changed = manifest_with_optional_index(updated)
    manifest_contract_metadata(updated)
    return (
        updated,
        metadata_changed,
        routing_changed,
        index_changed,
        legacy_optional_count if optional_routes_changed else 0,
    )


def _build_plan(project_root: Path, memory_dir: Path) -> tuple[MutationPlan, list[str], tuple[Path, ...]]:
    manifest_path = memory_dir / "manifest.md"
    original = read_managed_text(memory_dir, manifest_path)
    strict_protocol_metadata(original, allow_missing_section=True)
    metadata = protocol_metadata(original)
    version = metadata.get("protocol_version")
    if version:
        comparison = compare_versions(version, CURRENT_PROTOCOL_VERSION)
        if comparison is None:
            raise ValueError(f"Invalid protocol version {version!r}; review manifest.md manually.")
        if comparison > 0:
            raise ValueError(
                f"Project protocol {version} is newer than this CLI supports ({CURRENT_PROTOCOL_VERSION})."
            )
    entry_schema_version = entry_schema_version_for_manifest(original)
    seed_path: Path | None = None
    project_id = metadata.get("project_id")
    if project_id and not valid_project_id(project_id):
        raise ValueError(
            f"Invalid project_id {project_id!r}; review manifest.md manually."
        )
    provisional_project_id = project_id or "00000000-0000-4000-8000-000000000000"
    preflight_manifest, *_preflight_changes = _upgraded_manifest(
        original,
        provisional_project_id,
    )
    sources = _migration_sources(memory_dir, original)
    entry_sources = _entry_schema_sources(memory_dir)
    _validate_existing_formal_entries(
        project_root,
        memory_dir,
        entry_schema_version=entry_schema_version,
    )
    local_schema_migrations, local_schema_migrated_count, local_blockers = (
        _local_schema_migrations(
            project_root,
            memory_dir,
            project_id,
            entry_schema_version=entry_schema_version,
        )
    )
    schema_migrated: dict[str, str] = {}
    schema_migrated_count = 0
    if entry_schema_version != CURRENT_ENTRY_SCHEMA_VERSION:
        for relative, source in entry_sources.items():
            migrated_source, migrated_count = migrate_entry_schema(
                Path(relative),
                source,
                from_schema=entry_schema_version,
                to_schema=CURRENT_ENTRY_SCHEMA_VERSION,
            )
            if migrated_count:
                schema_migrated[relative] = migrated_source
                schema_migrated_count += migrated_count
    from .integrity import cross_unit_integrity_findings

    preflight_text = {
        memory_dir / relative: text
        for relative, text in schema_migrated.items()
    }
    preflight_text[memory_dir / "manifest.md"] = preflight_manifest
    cross_issues, _cross_warnings = cross_unit_integrity_findings(
        project_root,
        memory_dir,
        preflight_manifest,
        project_id=project_id,
        allow_missing_subjects=True,
        snapshot=build_snapshot(
            memory_dir,
            project_root,
            planned_text=preflight_text,
        ),
    )
    if cross_issues:
        preview = "; ".join(cross_issues[:5])
        suffix = f"; and {len(cross_issues) - 5} more" if len(cross_issues) > 5 else ""
        raise ValueError(
            "Migration candidate fails shared project integrity validation: "
            + preview
            + suffix
        )
    changelog_path = memory_dir / "changelog.md"
    changelog_original = (
        read_managed_text(memory_dir, changelog_path)
        if changelog_path.exists()
        else None
    )
    if not project_id:
        project_id, seed_path = pending_project_id(
            "migrate",
            project_root,
            digest_text(original),
        )
    suffixes, entry_seed_path = _migration_entry_seed(
        project_root,
        original,
        sources,
    )
    (
        updated,
        metadata_changed,
        routing_changed,
        index_changed,
        legacy_optional_count,
    ) = _upgraded_manifest(original, project_id)
    mutations: list[TextMutation] = []
    changes: list[str] = []

    def put_mutation(path: Path, text: str) -> None:
        for index, existing in enumerate(mutations):
            if existing.path == path:
                mutations[index] = TextMutation(path, text)
                return
        mutations.append(TextMutation(path, text))

    for relative, migrated_source in schema_migrated.items():
        put_mutation(memory_dir / relative, migrated_source)
    if schema_migrated_count:
        changes.append(
            "managed Entry files: migrate legacy bodies to the Entry schema 3 "
            "memory-custodian-body-v1 grammar"
        )
    if local_schema_migrated_count:
        changes.append(
            "bound local Entry files: migrate legacy bodies to the Entry schema 3 "
            "memory-custodian-body-v1 grammar"
        )
    if updated != original:
        put_mutation(manifest_path, updated)
    if metadata_changed or updated != original:
        changes.append("manifest.md: upgrade protocol metadata to 0.8/schema 3 and preserve/generate project_id")
    if routing_changed:
        changes.append("manifest.md: complete canonical task routing for Protocol 0.8")
    if index_changed:
        changes.append("manifest.md: add optional module index")
    if legacy_optional_count:
        changes.append("manifest.md: preserve legacy optional descriptions with explicit-only activation")

    subjects_path = memory_dir / "subjects.md"
    if not subjects_path.exists():
        put_mutation(subjects_path, render_template("subjects.md", today()))
        changes.append("subjects.md: create managed Subject registry scaffold")

    decisions_path = memory_dir / "decisions.md"
    manual_reports: list[str] = []
    migrated_count = 0
    used_entry_ids = {entry_id.casefold() for entry_id in memory_entry_ids(memory_dir)}
    if "decisions.md" in sources:
        decisions = schema_migrated.get("decisions.md", sources["decisions.md"])
        migrated, migrated_count, manual, generated = _migrate_decisions(
            decisions,
            suffixes,
            used_ids=used_entry_ids,
        )
        if migrated != decisions:
            put_mutation(decisions_path, migrated)
            changes.append(f"decisions.md: add stable IDs and legacy-unverified Evidence to {migrated_count} structured entries")
            changes.extend(f"decisions.md: generated Entry ID {entry_id}" for entry_id in generated)
        if manual:
            manual_reports.append(f"{manual} ambiguous decisions.md H2 section(s)")

    for relative in sorted(
        path for path in sources if path.startswith("areas/")
    ):
        area_path = memory_dir.joinpath(*Path(relative).parts)
        if relative not in sources:
            continue
        slug = Path(relative).stem
        area_original = schema_migrated.get(relative, sources[relative])
        area_updated, area_count, area_manual, area_generated = _migrate_decisions(
            area_original,
            suffixes,
            relative,
            scope=f"area:{slug}",
            code="AREA",
            used_ids=used_entry_ids,
        )
        if area_updated != area_original:
            put_mutation(area_path, area_updated)
            changes.append(
                f"{relative}: add stable area IDs and legacy-unverified Evidence to {area_count} structured entries"
            )
            changes.extend(f"{relative}: generated Entry ID {entry_id}" for entry_id in area_generated)
        if area_manual:
            manual_reports.append(f"{area_manual} ambiguous {relative} H2 section(s)")

    if changelog_original is not None and mutations:
        put_mutation(
            changelog_path,
            changelog_text(
                changelog_original,
                "Migrated project memory to Protocol 0.8 and Entry schema 3 "
                "without rewriting legacy freeform units.",
            ),
        )
    warnings = []
    for report in manual_reports:
        warnings.append(f"Manual migration recommended for {report}.")
    warnings.append("Legacy top-level bullets remain readable and are not mechanically rewritten.")
    if legacy_optional_count:
        warnings.append("Manual automatic-route mapping required for migrated optional modules.")
    if migrated_count or any("stable area IDs" in change for change in changes):
        warnings.append(
            "Manual Subject assignment required: review migrated managed entries, create explicit Subjects, "
            "and assign controlled Facets without inferring equivalence from titles."
        )
    planned_text = {mutation.path: mutation.text for mutation in mutations}
    final_snapshot = build_snapshot(
        memory_dir,
        project_root,
        planned_text=planned_text,
    )
    canonicalization_blockers: list[str] = []
    for item in final_snapshot.files:
        if item.archive:
            continue
        canonicalization_blockers.extend(item.check_issues)
        if item.relative in {
            "decisions.md", "constraints.md", "do-not-use.md", "preferences.md"
        } or item.relative.startswith("areas/"):
            document = item.markdown_document
            if document is not None:
                legacy_count = sum(
                    unit.kind == "bullet"
                    or (
                        unit.kind == "h2"
                        and not (
                            unit.heading
                            and ENTRY_ID_RE.search(unit.heading)
                        )
                    )
                    for unit in document.units
                )
                if legacy_count:
                    canonicalization_blockers.append(
                        f"{item.relative}: {legacy_count} active legacy entries require canonicalization"
                    )
    canonicalization_blockers.extend(final_snapshot.subject_parse_issues)
    canonicalization_blockers.extend(final_snapshot.subject_issues)
    canonicalization_blockers.extend(final_snapshot.reconciliation_parse_issues)
    canonicalization_blockers.extend(
        issue.message for issue in final_snapshot.reconciliation_issues
    )
    canonicalization_blockers.extend(final_snapshot.relation_issues)
    return (
        MutationPlan(
            "migrate",
            {"memory_dir": memory_dir.relative_to(project_root).as_posix()},
            project_id,
            CURRENT_PROTOCOL_VERSION,
            tuple(mutations),
            tuple(warnings),
            tuple(
                [
                    *(f"Manual migration required for {report}." for report in manual_reports),
                    *local_blockers,
                    *dict.fromkeys(canonicalization_blockers),
                ]
            ),
            project_root=project_root,
            private_mutations=local_schema_migrations,
        ),
        changes,
        tuple(path for path in (seed_path, entry_seed_path) if path is not None),
    )


def _run_finalize(
    args,
    *,
    migration_state_path: Path | None = None,
    source_project_id: str | None = None,
) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest_path = memory_dir / "manifest.md"
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory missing: {memory_dir}")
    if not manifest_path.exists():
        raise ValueError(f"manifest.md missing: {manifest_path}")

    plan, changes, seed_paths = _build_plan(project_root, memory_dir)
    if not plan.mutations and not plan.private_mutations:
        print("MemoryCustodian migrate: no changes needed")
        return 0
    print("MemoryCustodian migrate plan:")
    for change in changes:
        print(f"- {change}")
    print_plan(plan)
    if not args.apply:
        if plan.blockers:
            print("Dry run only. Resolve the migration blockers, then preview again.")
        else:
            print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
    if plan.blockers:
        print("Refusing migration apply while blockers remain.")
        return 1
    if not args.confirm_plan:
        raise ValueError("Protocol 0.8 migration finalize requires --confirm-plan <PLAN_ID>.")

    with project_mutation_guard(
        project_root,
        manifest_path,
        "migrate",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
        project_id_hint=plan.project_id,
        allow_metadata_repair=True,
    ) as guard:
        current, _changes, current_seed_paths = _build_plan(project_root, memory_dir)
        if current.blockers:
            print_plan(current)
            raise ValueError("Migration plan gained blockers before apply. No files written.")
        if guard.project_id != current.project_id:
            print_plan(current)
            raise ValueError(
                "Project identity changed before migration apply; preview again."
            )
        if current.plan_id != args.confirm_plan:
            print_plan(current)
            raise ValueError(
                f"Stale or mismatched plan: confirmed {args.confirm_plan}, current Plan ID is {current.plan_id}. No files written."
            )
        local_root = (
            overlay_directory(current.project_id).parent
            if current.private_mutations else None
        )
        if migration_state_path is None:
            apply_plan_transaction(
                current,
                memory_dir,
                local_root=local_root,
                force_journal=True,
            )
        else:
            apply_transaction(
                project_root=project_root,
                memory_root=memory_dir,
                project_id=(
                    source_project_id
                    if source_project_id and valid_project_id(source_project_id)
                    else None
                ),
                command="migrate-finalize",
                plan_id=current.plan_id,
                shared_mutations=tuple(current.mutations),
                private_mutations=tuple(current.private_mutations),
                local_root=local_root,
                migration_deletions=(PrivateDeleteMutation(
                    migration_state_path, migration_state_path.name
                ),),
                migration_root=migration_state_path.parent,
                force_journal=True,
            )
    for path in {*seed_paths, *current_seed_paths}:
        discard_pending_seed(path)
    print("Applied migration. Written files:")
    for mutation in current.mutations:
        print(f"- {mutation.path}")
    for mutation in current.private_mutations:
        print(f"- local/{mutation.relative}")
    return 0


def _migration_state_path(project_root: Path, memory_dir: Path) -> Path:
    binding = bootstrap_binding_id(project_root, memory_dir)
    return private_state_directory("migrations") / f"{binding}.json"


def _raw_file_bytes(path: Path) -> bytes:
    """Read one regular file without following its final symlink."""

    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"Migration source is missing: {path}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Migration source must be a regular non-symlink file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"Migration source changed during safe open: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(_raw_file_bytes(path)).hexdigest()


def _json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _entry_checklist_for_text(
    path: str,
    text: str,
    *,
    entry_schema_version: str,
    storage: str = "shared",
) -> list[dict[str, object]]:
    """Describe source units without inventing title, identity, or semantics."""

    document = parse_markdown_units(text)
    checklist: list[dict[str, object]] = []
    for unit_index, unit in enumerate(document.units):
        if unit.kind not in {"h2", "bullet", "ambiguous-bullet"}:
            continue
        entry = None
        try:
            parsed = parse_structured_entries(
                Path(path), unit.text, entry_schema_version=entry_schema_version,
            )
            if len(parsed) == 1:
                entry = parsed[0]
        except (OSError, RuntimeError, ValueError):
            entry = None
        first_line = unit.text.splitlines()[0] if unit.text.splitlines() else ""
        canonical = bool(
            unit.kind == "h2"
            and ENTRY_ID_RE.search(first_line)
            and heading_entry_ids(unit.text)
        )
        actions: list[str] = []
        if not canonical:
            actions.append("canonicalization")
        if entry is not None:
            if not entry.evidence:
                actions.append("evidence")
            if (
                entry.status == "active"
                and entry.entry_id.split("-", 2)[1].upper() not in {"INBOX", "TOMB", "DNU"}
                and entry.scope not in {"local-user", "local-machine"}
            ):
                if not entry.fields.get("Subject"):
                    actions.append("subject")
                if not entry.fields.get("Facet"):
                    actions.append("facet")
            relation_fields = {
                name: value
                for name, value in entry.fields.items()
                if name in {"Supersedes", "Promoted-From", "Exception-To", "Merged-Into"}
            }
        else:
            relation_fields = {}
        checklist.append({
            "storage": storage,
            "path": path,
            "unit_index": unit_index,
            "unit_kind": unit.kind,
            "entry_id": entry.entry_id if entry is not None else None,
            "title": entry.title if entry is not None else None,
            "canonical": canonical,
            "evidence": bool(entry is not None and entry.evidence),
            "subject": bool(entry is not None and entry.fields.get("Subject")),
            "facet": bool(entry is not None and entry.fields.get("Facet")),
            "relations": relation_fields,
            "required_actions": actions,
        })
    return checklist


def _source_binding(
    project_root: Path,
    memory_dir: Path,
    manifest: str,
    metadata: dict[str, str],
) -> tuple[dict[str, object], dict[str, object]]:
    """Capture all shared bytes and the inspected bound local snapshot."""

    shared: dict[str, str] = {}
    shared_text: dict[str, str] = {}
    for path in managed_markdown_files(memory_dir):
        relative = path.relative_to(memory_dir).as_posix()
        shared[relative] = _raw_sha256(path)
        shared_text[relative] = read_managed_text(memory_dir, path)

    local: dict[str, str] = {}
    local_snapshot: dict[str, object] = {
        "status": LocalStatus.DISABLED.value,
        "project_id": metadata.get("project_id"),
        "files": {},
        "warnings": [],
    }
    local_text: dict[str, str] = {}
    project_id = metadata.get("project_id")
    if project_id and valid_project_id(project_id):
        try:
            overlay = inspect_overlay(
                project_root,
                project_id,
                entry_schema_version=entry_schema_version_for_manifest(manifest),
                capture_unbound=True,
            )
            local_snapshot["status"] = overlay.status.value
            local_snapshot["warnings"] = list(overlay.warnings)
            if overlay.snapshot is not None:
                for captured in overlay.snapshot.files:
                    local[captured.relative] = _raw_sha256(captured.path)
                    local_text[captured.relative] = captured.text
        except (OSError, RuntimeError, ValueError) as exc:
            local_snapshot["status"] = LocalStatus.REVIEW.value
            local_snapshot["warnings"] = [str(exc)]
    local_snapshot["files"] = dict(sorted(local.items()))
    local_snapshot["snapshot_sha256"] = _json_sha256(local_snapshot["files"])
    digest_payload = {
        "shared": dict(sorted(shared.items())),
        "local": dict(sorted(local.items())),
    }
    source = {
        "shared": dict(sorted(shared.items())),
        "local": dict(sorted(local.items())),
    }
    flattened = {
        **{f"shared/{key}": value for key, value in sorted(shared.items())},
        **{f"local/{key}": value for key, value in sorted(local.items())},
    }
    binding = {
        "source_raw_byte_digests": source,
        "source_digests": flattened,
        "source_snapshot_sha256": _json_sha256(digest_payload),
        "local_snapshot": local_snapshot,
        "local_text": local_text,
        "shared_text": shared_text,
    }
    return binding, {
        "shared": shared_text,
        "local": local_text,
    }


def _migration_checklist(
    source_text: dict[str, dict[str, str]],
    *,
    entry_schema_version: str,
) -> list[dict[str, object]]:
    checklist: list[dict[str, object]] = []
    for path, text in sorted(source_text.get("shared", {}).items()):
        checklist.extend(_entry_checklist_for_text(
            path, text, entry_schema_version=entry_schema_version, storage="shared",
        ))
    for path, text in sorted(source_text.get("local", {}).items()):
        checklist.extend(_entry_checklist_for_text(
            path, text, entry_schema_version=entry_schema_version, storage="local",
        ))
    return checklist


def _stage_payload(project_root: Path, memory_dir: Path) -> dict[str, object]:
    manifest_path = memory_dir / "manifest.md"
    manifest = read_managed_text(memory_dir, manifest_path)
    metadata = strict_protocol_metadata(manifest, allow_missing_section=True)
    route_issues = validate_manifest_routes(manifest)
    fatal_route_issues = [
        issue
        for issue in route_issues
        if "expected one canonical heading; candidates: none" not in issue
    ]
    if fatal_route_issues:
        raise ValueError("Invalid manifest routing: " + "; ".join(fatal_route_issues))
    project_id = metadata.get("project_id")
    binding, source_text = _source_binding(project_root, memory_dir, manifest, metadata)
    local_snapshot = binding["local_snapshot"]
    local_files = local_snapshot.get("files", {}) if isinstance(local_snapshot, dict) else {}
    local_digest = (
        local_files.get("manifest.md")
        if isinstance(local_files, dict) else None
    )
    source_protocol_version = metadata.get("protocol_version", "0.5")
    source_entry_schema_version = metadata.get("entry_schema_version", "1")
    checklist = _migration_checklist(
        source_text,
        entry_schema_version=entry_schema_version_for_manifest(manifest),
    )
    source = binding["source_raw_byte_digests"]
    return {
        "migration_state_schema_version": 1,
        "binding_id": bootstrap_binding_id(project_root, memory_dir),
        "project_id": project_id,
        "normalized_project_root": str(project_root.resolve()),
        "normalized_memory_root": str(memory_dir.resolve()),
        "source_protocol_version": source_protocol_version,
        "source_entry_schema_version": source_entry_schema_version,
        "manifest_sha256": digest_text(manifest),
        "manifest_raw_sha256": binding["source_raw_byte_digests"]["shared"].get("manifest.md"),
        "local_manifest_sha256": local_digest,
        "source_raw_byte_digests": source,
        "source_digests": binding["source_digests"],
        "source_snapshot_sha256": binding["source_snapshot_sha256"],
        "local_snapshot": local_snapshot,
        "prepare_result_digests": {
            "manifest_sha256": digest_text(manifest),
            "manifest_raw_sha256": binding["source_raw_byte_digests"]["shared"].get("manifest.md"),
            "source_snapshot_sha256": binding["source_snapshot_sha256"],
            "local_snapshot_sha256": local_snapshot.get("snapshot_sha256"),
        },
        "entry_checklist": checklist,
    }


def _stage_plan_id(stage: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {"stage": stage, **payload}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _binding_mismatches(
    state: dict[str, object],
    current: dict[str, object],
    *,
    include_source: bool,
) -> list[str]:
    """Compare the opaque prepare binding without silently accepting drift."""

    mismatches: list[str] = []
    for key in (
        "migration_state_schema_version",
        "binding_id",
        "project_id",
        "normalized_project_root",
        "normalized_memory_root",
        "source_protocol_version",
        "source_entry_schema_version",
    ):
        if state.get(key) != current.get(key):
            mismatches.append(key)
    if include_source:
        for key in (
            "manifest_raw_sha256",
            "source_raw_byte_digests",
            "source_digests",
            "source_snapshot_sha256",
            "local_snapshot",
        ):
            if state.get(key) != current.get(key):
                mismatches.append(key)
    return mismatches


def _canonicalize_source_digest(
    current: dict[str, object],
    selector: str,
) -> str:
    source_digests = current.get("source_digests")
    if not isinstance(source_digests, dict):
        raise ValueError("Migration state has no complete source digest binding.")
    prefix = selector.split(":", 1)[0].replace("\\", "/")
    digest = source_digests.get(f"shared/{prefix}")
    if not isinstance(digest, str):
        raise ValueError("Legacy selector is not present in the bound source digest set.")
    return digest


def _canonicalize_entry_id(
    kind: str,
    selector: str,
    source_digest: str,
    suffixes: dict[str, str],
) -> str:
    codes = {
        "decision": "DEC", "constraint": "CON", "preference": "PREF",
        "tombstone": "TOMB", "do-not-use": "DNU", "area": "AREA",
        "rule": "AREA", "profile": "AREA",
    }
    code = codes.get(kind)
    if code is None:
        raise ValueError(f"Unsupported legacy canonicalization type: {kind}")
    key = hashlib.sha256(
        f"{selector}\0{source_digest}\0{kind}".encode("utf-8")
    ).hexdigest()
    suffix = suffixes.get(key) or key[:8]
    return f"MC-{code}-19700101-{suffix}"


def _canonicalize_args_descriptor(args) -> dict[str, object]:
    return {
        "from_legacy": getattr(args, "from_legacy", None),
        "type": getattr(args, "type", None),
        "title": getattr(args, "title", None),
        "scope": getattr(args, "scope", None),
        "subject": getattr(args, "subject", None),
        "facet": getattr(args, "facet", None),
        "reason": getattr(args, "reason", None),
        "evidence": list(getattr(args, "evidence", ()) or ()),
    }


def _binding_after_shared_mutations(
    current: dict[str, object],
    memory_dir: Path,
    mutations: list[TextMutation],
) -> dict[str, object]:
    """Predict the raw-byte source binding after a canonicalize transaction."""

    raw = current.get("source_raw_byte_digests")
    if not isinstance(raw, dict):
        raise ValueError("Migration state has no complete source digest binding.")
    shared = raw.get("shared")
    local = raw.get("local")
    if not isinstance(shared, dict) or not isinstance(local, dict):
        raise ValueError("Migration state has no complete source digest binding.")
    shared_after = dict(shared)
    for mutation in mutations:
        relative = mutation.path.relative_to(memory_dir).as_posix()
        output = mutation.text if mutation.text.endswith("\n") else mutation.text + "\n"
        shared_after[relative] = hashlib.sha256(output.encode("utf-8")).hexdigest()
    raw_after = {
        "shared": dict(sorted(shared_after.items())),
        "local": dict(sorted(local.items())),
    }
    flattened = {
        **{f"shared/{key}": value for key, value in raw_after["shared"].items()},
        **{f"local/{key}": value for key, value in raw_after["local"].items()},
    }
    snapshot = _json_sha256(raw_after)
    local_snapshot = current.get("local_snapshot")
    if isinstance(local_snapshot, dict):
        local_snapshot_after = dict(local_snapshot)
    else:
        local_snapshot_after = {"files": dict(raw_after["local"])}
    local_snapshot_after["files"] = dict(raw_after["local"])
    local_snapshot_after["snapshot_sha256"] = _json_sha256(raw_after["local"])
    return {
        "source_raw_byte_digests": raw_after,
        "source_digests": flattened,
        "source_snapshot_sha256": snapshot,
        "local_snapshot": local_snapshot_after,
        "manifest_raw_sha256": raw_after["shared"].get("manifest.md"),
        "manifest_sha256": current.get("manifest_sha256"),
    }


def _prepare_preflight(project_root: Path, memory_dir: Path) -> None:
    """Reject unsafe or malformed source operands before private state exists."""

    manifest = read_managed_text(memory_dir, memory_dir / "manifest.md")
    metadata = strict_protocol_metadata(manifest, allow_missing_section=True)
    project_id = metadata.get("project_id")
    if project_id and not valid_project_id(project_id):
        raise ValueError(
            f"Invalid project_id {project_id!r}; review manifest.md manually."
        )
    entry_schema_version = entry_schema_version_for_manifest(manifest)
    # Source discovery owns optional-route containment, symlink, and decoding
    # checks.  Formal-entry validation must also precede creation of the
    # bootstrap binding salt or migration checkpoint.
    _migration_sources(memory_dir, manifest)
    _validate_existing_formal_entries(
        project_root,
        memory_dir,
        entry_schema_version=entry_schema_version,
    )


def _prepare(args, project_root: Path, memory_dir: Path) -> int:
    _prepare_preflight(project_root, memory_dir)
    payload = _stage_payload(project_root, memory_dir)
    if (
        payload["source_protocol_version"] == CURRENT_PROTOCOL_VERSION
        and payload["source_entry_schema_version"] == CURRENT_ENTRY_SCHEMA_VERSION
    ):
        manifest = read_managed_text(memory_dir, memory_dir / "manifest.md")
        try:
            manifest_contract_metadata(manifest)
        except ValueError as exc:
            raise ValueError(
                "Current Protocol 0.8 metadata is incomplete or invalid; "
                "repair it before migration."
            ) from exc
        if not (memory_dir / "subjects.md").is_file():
            raise ValueError(
                "Current Protocol 0.8 requires subjects.md; run "
                "`memory-custodian init --repair`."
            )
        print("MemoryCustodian migration prepare: project is already Protocol 0.8 / Entry schema 3.")
        return 0
    plan_id = _stage_plan_id("prepare", payload)
    print("MemoryCustodian migration prepare:")
    print(f"- Source protocol: {payload['source_protocol_version']}")
    print(f"- Source Entry schema: {payload['source_entry_schema_version']}")
    print("- Shared protocol metadata remains unchanged during prepare.")
    print("- Manual Subject, Facet, Evidence, relation, and legacy-entry review may be required.")
    print(f"Plan ID: {plan_id}")
    if not args.apply:
        print("Dry run only. Re-run with --prepare --apply --confirm-plan <PLAN_ID>.")
        return 0
    if args.confirm_plan != plan_id:
        raise ValueError("Stale or mismatched migration prepare plan.")
    path = _migration_state_path(project_root, memory_dir)
    with project_mutation_guard(
        project_root, memory_dir / "manifest.md", "migrate prepare",
        timeout=args.lock_timeout, break_stale=args.break_stale_lock,
        allow_legacy=True,
        allow_metadata_repair=True,
    ):
        current = _stage_payload(project_root, memory_dir)
        current_plan_id = _stage_plan_id("prepare", current)
        if current_plan_id != args.confirm_plan:
            raise ValueError("Migration source changed before prepare apply; preview again.")
        apply_transaction(
            project_root=project_root, memory_root=memory_dir,
            project_id=None, command="migrate-prepare", plan_id=current_plan_id,
            migration_mutations=(PrivateTextMutation(
                path, path.name, json.dumps(current, sort_keys=True) + "\n"
            ),),
            migration_root=path.parent, force_journal=True,
        )
    print("Prepared repo-external migration state; shared memory was not changed.")
    return 0


def _canonicalize(args, project_root: Path, memory_dir: Path) -> int:
    path = _migration_state_path(project_root, memory_dir)
    if not path.exists():
        raise ValueError("Migration is not prepared; run `migrate --prepare` first.")
    state = json.loads(read_private_file(path))
    if not isinstance(state, dict):
        raise ValueError("Migration state is malformed; run `migrate --prepare` again.")
    current = _stage_payload(project_root, memory_dir)
    binding_mismatches = _binding_mismatches(state, current, include_source=False)
    if binding_mismatches:
        raise ValueError(
            "Migration state binding is stale or belongs to a different project: "
            + ", ".join(binding_mismatches)
        )
    plan, changes, _seed_paths = _build_plan(project_root, memory_dir)
    explicit_mutations: list[TextMutation] = []
    target_only_metadata: list[dict[str, object]] = []
    canonicalize_seed: Path | None = None
    canonicalized_entry: dict[str, object] | None = None
    if getattr(args, "from_legacy", None):
        from .add import build_from_legacy_mutations

        selector = str(args.from_legacy)
        source_digest = _canonicalize_source_digest(current, selector)
        key = hashlib.sha256(
            f"{selector}\0{source_digest}\0{getattr(args, 'type', '')}".encode("utf-8")
        ).hexdigest()
        suffixes, canonicalize_seed = pending_entry_suffixes(
            "migrate-canonicalize",
            project_root,
            str(current["source_snapshot_sha256"]),
            [key],
        )
        fixed_id = _canonicalize_entry_id(
            str(args.type), selector, source_digest, {key: suffixes[key]},
        )
        explicit_mutations, target, new_id, _rendered = build_from_legacy_mutations(
            args,
            project_root,
            memory_dir,
            fixed_id=fixed_id,
            entry_schema_version=str(current["source_entry_schema_version"]),
        )
        canonicalized_entry = {
            "entry_id": new_id,
            "path": target,
            "type": args.type,
            "selector": selector,
            "source_digest": source_digest,
        }
        if (
            str(args.type) in {"area", "rule", "profile"}
            and str(current["source_entry_schema_version"]) != CURRENT_ENTRY_SCHEMA_VERSION
        ):
            target_only_metadata.append({
                "entry_id": new_id,
                "path": target,
                "entry_type": {
                    "area": "decision", "rule": "rule", "profile": "profile",
                }[str(args.type)],
            })
        changes = [*changes, f"{target}: canonicalize explicit legacy H2 unit {selector}"]
    mutation_digest = [
        {
            "path": mutation.path.relative_to(memory_dir).as_posix(),
            "sha256": digest_text(mutation.text),
        }
        for mutation in explicit_mutations
    ]
    payload = {
        "state": state,
        "current_binding": {
            "manifest_raw_sha256": current["manifest_raw_sha256"],
            "source_snapshot_sha256": current["source_snapshot_sha256"],
            "source_digests": current["source_digests"],
            "local_snapshot": current["local_snapshot"],
        },
        "blockers": list(plan.blockers),
        "args": _canonicalize_args_descriptor(args),
        "mutations": mutation_digest,
        "target_only_metadata": target_only_metadata,
    }
    plan_id = _stage_plan_id("canonicalize", payload)
    print("MemoryCustodian migration canonicalization checklist:")
    for change in changes or ["No mechanical source rewrite is currently available."]:
        print(f"- {change}")
    checklist = current.get("entry_checklist", [])
    if isinstance(checklist, list):
        print(f"- Entry checklist items: {len(checklist)}")
        for item in checklist:
            if not isinstance(item, dict):
                continue
            actions = item.get("required_actions") or []
            if actions:
                print(
                    f"- CHECKLIST: {item.get('storage')} {item.get('path')}#unit-{item.get('unit_index')}: "
                    + ", ".join(str(action) for action in actions)
                )
    for blocker in plan.blockers:
        print(f"- BLOCKER: {blocker}")
    for item in target_only_metadata:
        print(f"- TARGET-ONLY: {item['entry_id']} Entry-Type={item['entry_type']} (deferred to finalize)")
    print(f"Plan ID: {plan_id}")
    if not args.apply:
        print("Dry run only. Explicit semantic inputs remain required for ambiguous entries.")
        return 0
    if args.confirm_plan != plan_id:
        raise ValueError("Stale or mismatched migration canonicalize plan.")
    post_binding = _binding_after_shared_mutations(
        current, memory_dir, explicit_mutations,
    )
    updated_state = dict(state)
    updated_state["canonicalize_manifest_sha256"] = post_binding["manifest_sha256"]
    updated_state["canonicalize_manifest_raw_sha256"] = post_binding["manifest_raw_sha256"]
    updated_state["canonicalize_source_raw_byte_digests"] = post_binding["source_raw_byte_digests"]
    updated_state["canonicalize_source_digests"] = post_binding["source_digests"]
    updated_state["canonicalize_source_snapshot_sha256"] = post_binding["source_snapshot_sha256"]
    updated_state["canonicalize_local_snapshot"] = post_binding["local_snapshot"]
    updated_state["canonicalize_entry_checklist"] = current.get("entry_checklist", [])
    existing_target_only = updated_state.get("target_only_metadata", [])
    if not isinstance(existing_target_only, list):
        existing_target_only = []
    existing_by_id = {
        str(item.get("entry_id")).casefold(): item
        for item in existing_target_only
        if isinstance(item, dict) and item.get("entry_id")
    }
    for item in target_only_metadata:
        existing_by_id[str(item["entry_id"]).casefold()] = item
    updated_state["target_only_metadata"] = [
        existing_by_id[key] for key in sorted(existing_by_id)
    ]
    applied = False
    with project_mutation_guard(
        project_root, memory_dir / "manifest.md", "migrate canonicalize",
        timeout=args.lock_timeout, break_stale=args.break_stale_lock,
        allow_legacy=True,
        allow_metadata_repair=True,
        project_id_hint=(str(state.get("project_id")) if state.get("project_id") else None),
    ) as guard:
        latest = _stage_payload(project_root, memory_dir)
        if _binding_mismatches(current, latest, include_source=True):
            raise ValueError("Migration source changed before canonicalize apply; preview again.")
        latest_mutations: list[TextMutation] = []
        if getattr(args, "from_legacy", None):
            from .add import build_from_legacy_mutations

            latest_mutations, latest_target, latest_id, _latest_rendered = build_from_legacy_mutations(
                args,
                project_root,
                memory_dir,
                fixed_id=canonicalized_entry["entry_id"] if canonicalized_entry else None,
                entry_schema_version=str(latest["source_entry_schema_version"]),
            )
            latest_descriptor = [
                {
                    "path": mutation.path.relative_to(memory_dir).as_posix(),
                    "sha256": digest_text(mutation.text),
                }
                for mutation in latest_mutations
            ]
            if latest_descriptor != mutation_digest:
                raise ValueError("Legacy source changed before canonicalize apply; preview again.")
            if canonicalized_entry is not None:
                canonicalized_entry = {
                    **canonicalized_entry,
                    "path": latest_target,
                    "entry_id": latest_id,
                }
        latest_payload = {
            "state": state,
            "current_binding": {
                "manifest_raw_sha256": latest["manifest_raw_sha256"],
                "source_snapshot_sha256": latest["source_snapshot_sha256"],
                "source_digests": latest["source_digests"],
                "local_snapshot": latest["local_snapshot"],
            },
            "blockers": list(plan.blockers),
            "args": _canonicalize_args_descriptor(args),
            "mutations": mutation_digest,
            "target_only_metadata": target_only_metadata,
        }
        latest_plan_id = _stage_plan_id("canonicalize", latest_payload)
        if latest_plan_id != args.confirm_plan:
            raise ValueError("Migration source or canonicalization inputs changed before apply; preview again.")
        apply_transaction(
            project_root=project_root, memory_root=memory_dir,
            project_id=(
                str(state.get("project_id"))
                if valid_project_id(str(state.get("project_id", ""))) else None
            ),
            command="migrate-canonicalize", plan_id=plan_id,
            shared_mutations=tuple(latest_mutations),
            migration_mutations=(PrivateTextMutation(
                path, path.name, json.dumps(updated_state, sort_keys=True) + "\n"
            ),), migration_root=path.parent, force_journal=True,
        )
        applied = True
    if applied and canonicalize_seed is not None:
        discard_pending_seed(canonicalize_seed)
    if canonicalized_entry is not None:
        print(f"Canonicalized explicit legacy entry {canonicalized_entry['entry_id']} in {canonicalized_entry['path']}.")
    else:
        print("Canonicalization checkpoint recorded; no semantic facts were inferred.")
    return 0


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if args.prepare:
        return _prepare(args, project_root, memory_dir)
    if args.canonicalize:
        return _canonicalize(args, project_root, memory_dir)
    state_path = _migration_state_path(project_root, memory_dir)
    if not state_path.exists():
        raise ValueError("Migration finalize requires a prepared migration state.")
    state = json.loads(read_private_file(state_path))
    if not isinstance(state, dict):
        raise ValueError("Migration state is malformed; run `migrate --prepare` again.")
    current = _stage_payload(project_root, memory_dir)
    binding_mismatches = _binding_mismatches(state, current, include_source=False)
    if binding_mismatches:
        raise ValueError(
            "Migration state binding is stale or belongs to a different project: "
            + ", ".join(binding_mismatches)
        )
    if "canonicalize_manifest_sha256" not in state:
        raise ValueError(
            "Migration finalize requires an applied canonicalization checkpoint."
        )
    canonicalize_binding = {
        "manifest_raw_sha256": state.get("canonicalize_manifest_raw_sha256"),
        "source_raw_byte_digests": state.get("canonicalize_source_raw_byte_digests"),
        "source_digests": state.get("canonicalize_source_digests"),
        "source_snapshot_sha256": state.get("canonicalize_source_snapshot_sha256"),
        "local_snapshot": state.get("canonicalize_local_snapshot"),
    }
    current_binding = {
        key: current.get(key)
        for key in (
            "manifest_raw_sha256", "source_raw_byte_digests", "source_digests",
            "source_snapshot_sha256", "local_snapshot",
        )
    }
    if state.get("canonicalize_manifest_sha256") != current.get("manifest_sha256") or canonicalize_binding != current_binding:
        raise ValueError(
            "Migration source changed after canonicalization; run canonicalize again."
        )
    return _run_finalize(
        args,
        migration_state_path=state_path,
        source_project_id=(str(state.get("project_id")) if state.get("project_id") else None),
    )
