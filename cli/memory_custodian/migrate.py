"""Conservative, preview-first migration to the current Protocol 0.7 contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
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
)
from .markdown import visible_lines
from .mutations import (
    PrivateTextMutation,
    TextMutation,
    apply_mutations,
    apply_private_mutations,
    restore_text_file_exact,
)
from .local_overlay import LocalStatus, inspect_overlay
from .plans import (
    MutationPlan,
    digest_text,
    discard_pending_seed,
    pending_project_id,
    pending_entry_suffixes,
    print_plan,
)
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
    strict_protocol_metadata,
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
            "managed Entry files: encode schema 1 bodies with the schema 2 "
            "memory-custodian-body-v1 grammar"
        )
    if local_schema_migrated_count:
        changes.append(
            "bound local Entry files: encode schema 1 bodies with the schema 2 "
            "memory-custodian-body-v1 grammar"
        )
    if updated != original:
        put_mutation(manifest_path, updated)
    if metadata_changed or updated != original:
        changes.append("manifest.md: upgrade protocol metadata to 0.7 and preserve/generate project_id")
    if routing_changed:
        changes.append("manifest.md: complete canonical task routing for Protocol 0.7")
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
                "Migrated project memory to Protocol 0.7 and Entry schema 2 "
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
                ]
            ),
            project_root=project_root,
            private_mutations=local_schema_migrations,
        ),
        changes,
        tuple(path for path in (seed_path, entry_seed_path) if path is not None),
    )


def run(args) -> int:
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
        raise ValueError("Protocol 0.7 migration apply requires --confirm-plan <PLAN_ID>.")

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
        # Migration is the one multi-root operation that can change the
        # parser selected by the shared manifest.  Capture exact preimages
        # before writing anything, keep the manifest's schema flip last among
        # shared writes, and restore every operand on any failure.  This is
        # intentionally separate from the general MutationPlan writer: its
        # normal partial-write behavior remains unchanged.
        preimages = _capture_migration_preimages(
            memory_dir,
            tuple(current.mutations),
            tuple(current.private_mutations),
        )
        non_manifest = tuple(
            mutation
            for mutation in current.mutations
            if mutation.path != manifest_path
        )
        manifest_mutations = tuple(
            mutation
            for mutation in current.mutations
            if mutation.path == manifest_path
        )
        try:
            if non_manifest:
                apply_mutations(list(non_manifest))
            if current.private_mutations:
                apply_private_mutations(list(current.private_mutations))
            if manifest_mutations:
                apply_mutations(list(manifest_mutations))
        except Exception as exc:
            recovery_failures = _restore_migration_preimages(
                preimages,
                manifest_path,
            )
            if recovery_failures:
                details = "; ".join(recovery_failures)
                raise ValueError(
                    "Migration apply failed and recovery was partial; schema 1 "
                    f"preimages could not be restored for: {details}. "
                    "Inspect the listed files before retrying."
                ) from exc
            raise ValueError(
                "Migration apply failed; all shared and local files were restored "
                "to their schema 1 preimages. No migration was applied."
            ) from exc
    for path in {*seed_paths, *current_seed_paths}:
        discard_pending_seed(path)
    print("Applied migration. Written files:")
    for mutation in current.mutations:
        print(f"- {mutation.path}")
    for mutation in current.private_mutations:
        print(f"- local/{mutation.relative}")
    return 0
