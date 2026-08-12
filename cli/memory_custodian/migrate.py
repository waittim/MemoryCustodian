"""Conservative, preview-first Protocol 0.5 to 0.6 migration."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat

from .entries import (
    ENTRY_ID_RE,
    VALID_SCOPES_RE,
    entry_unit_issues,
    heading_entry_ids,
    line_safe_markdown_body,
    memory_entry_ids,
    parse_structured_entries,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    validate_evidence,
)
from .locking import project_mutation_guard
from .markdown import visible_lines
from .mutations import TextMutation, apply_mutations
from .plans import (
    MutationPlan,
    digest_text,
    discard_pending_seed,
    pending_project_id,
    pending_entry_suffixes,
    print_plan,
)
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    changelog_text,
    compare_versions,
    manifest_with_complete_task_routing,
    manifest_with_current_protocol_metadata,
    manifest_with_current_task_routing,
    manifest_contract_metadata,
    manifest_with_optional_index,
    manifest_with_protocol_07_optional_routes,
    managed_markdown_files,
    MarkdownUnit,
    parse_markdown_units,
    protocol_metadata,
    strict_protocol_metadata,
    valid_project_id,
    resolve_memory_dir,
    resolve_project_root,
    render_markdown_document,
    today,
)
from .routes import parse_optional_module_index
from .templates import render_template


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
    updated: list[MarkdownUnit] = []
    generated_ids: list[str] = []
    for index, unit in enumerate(document.units):
        if unit.kind != "h2":
            updated.append(unit)
            continue
        section = unit.text
        if ENTRY_ID_RE.search(section.splitlines()[0]):
            updated.append(unit)
            continue
        visible = {line.index: line.text for line in visible_lines(section)}
        if not any(line.strip() == "Decision:" for line in visible.values()):
            manual += 1
            updated.append(unit)
            continue
        entry_id = _legacy_id(relative, section, index, code, suffixes)
        if entry_id.casefold() in occupied_ids:
            manual += 1
            updated.append(unit)
            continue
        lines = section.splitlines()
        title = re.sub(r"^##\s+(?:\d{4}-\d{2}-\d{2}\s+-\s+)?", "", lines[0]).strip()
        safe_body = []
        for line_index, line in enumerate(lines[1:], start=1):
            if line_index not in visible or line in {"Decision:", "Reason:"}:
                safe_body.append(line)
            else:
                safe_body.append(line_safe_markdown_body(line))
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
        parsed = parse_structured_entries(Path(relative), migrated)
        if len(parsed) != 1 or parsed[0].entry_id.casefold() != entry_id.casefold():
            manual += 1
            updated.append(unit)
            continue
        validation_issues = [
            *structured_entry_schema_issues(parsed[0], relative),
            *structured_entry_storage_issues(parsed[0], relative),
        ]
        if validation_issues:
            manual += 1
            updated.append(unit)
            continue
        generated_ids.append(entry_id)
        occupied_ids.add(entry_id.casefold())
        updated.append(MarkdownUnit("h2", migrated, migrated.splitlines()[0][3:].strip()))
        changed += 1
    rendered = render_markdown_document(document, updated) if changed else text
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
        try:
            resolved_path = path.resolve()
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
        if path.exists() or path.is_symlink():
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"Migration operand must be a regular non-symlink file: {relative}"
                )
            sources[relative] = path.read_text(encoding="utf-8")
    return sources


def _validate_existing_formal_entries(project_root: Path, memory_dir: Path) -> None:
    """Reject formal Entries that an upgrade would otherwise grandfather as 0.7."""

    issues: list[str] = []
    id_counts: dict[str, int] = {}
    for path in managed_markdown_files(memory_dir):
        relative = path.relative_to(memory_dir).as_posix()
        text = path.read_text(encoding="utf-8")
        issues.extend(entry_unit_issues(text, relative))
        for entry_id in heading_entry_ids(text):
            key = entry_id.casefold()
            id_counts[key] = id_counts.get(key, 0) + 1
        for entry in parse_structured_entries(path, text):
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
    original = manifest_path.read_text(encoding="utf-8")
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
    _validate_existing_formal_entries(project_root, memory_dir)
    from .check import cross_unit_integrity_findings

    cross_issues, _cross_warnings = cross_unit_integrity_findings(
        project_root,
        memory_dir,
        preflight_manifest,
        project_id=project_id,
        allow_missing_subjects=True,
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
        changelog_path.read_text(encoding="utf-8")
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
    if updated != original:
        mutations.append(TextMutation(manifest_path, updated))
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
        mutations.append(TextMutation(subjects_path, render_template("subjects.md", today())))
        changes.append("subjects.md: create managed Subject registry scaffold")

    decisions_path = memory_dir / "decisions.md"
    manual_reports: list[str] = []
    migrated_count = 0
    used_entry_ids = {entry_id.casefold() for entry_id in memory_entry_ids(memory_dir)}
    if "decisions.md" in sources:
        decisions = sources["decisions.md"]
        migrated, migrated_count, manual, generated = _migrate_decisions(
            decisions,
            suffixes,
            used_ids=used_entry_ids,
        )
        if migrated != decisions:
            mutations.append(TextMutation(decisions_path, migrated))
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
        area_original = sources[relative]
        area_updated, area_count, area_manual, area_generated = _migrate_decisions(
            area_original,
            suffixes,
            relative,
            scope=f"area:{slug}",
            code="AREA",
            used_ids=used_entry_ids,
        )
        if area_updated != area_original:
            mutations.append(TextMutation(area_path, area_updated))
            changes.append(
                f"{relative}: add stable area IDs and legacy-unverified Evidence to {area_count} structured entries"
            )
            changes.extend(f"{relative}: generated Entry ID {entry_id}" for entry_id in area_generated)
        if area_manual:
            manual_reports.append(f"{area_manual} ambiguous {relative} H2 section(s)")

    if changelog_original is not None and mutations:
        mutations.append(
            TextMutation(
                changelog_path,
                changelog_text(
                    changelog_original,
                    "Migrated project memory to Protocol 0.7 without rewriting legacy freeform units.",
                ),
            )
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
            tuple(f"Manual migration required for {report}." for report in manual_reports),
            project_root=project_root,
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
    if not plan.mutations:
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
        apply_mutations(list(current.mutations))
    for path in {*seed_paths, *current_seed_paths}:
        discard_pending_seed(path)
    print("Applied migration. Written files:")
    for mutation in current.mutations:
        print(f"- {mutation.path}")
    return 0
