"""Conservative, preview-first Protocol 0.5 to 0.6 migration."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .entries import ENTRY_ID_RE, split_h2
from .locking import project_mutation_guard
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
    manifest_with_current_protocol_metadata,
    manifest_with_current_task_routing,
    manifest_with_optional_index,
    manifest_with_protocol_07_optional_routes,
    optional_index_paths,
    project_id_from_manifest,
    protocol_contract_metadata,
    protocol_metadata,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
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
) -> tuple[str, int, int, tuple[str, ...]]:
    preamble, sections = split_h2(text)
    changed = 0
    manual = 0
    updated = []
    generated_ids: list[str] = []
    for index, section in enumerate(sections):
        if ENTRY_ID_RE.search(section.splitlines()[0]):
            updated.append(section)
            continue
        if "Decision:" not in section:
            manual += 1
            updated.append(section)
            continue
        entry_id = _legacy_id(relative, section, index, code, suffixes)
        generated_ids.append(entry_id)
        lines = section.splitlines()
        title = re.sub(r"^##\s+(?:\d{4}-\d{2}-\d{2}\s+-\s+)?", "", lines[0]).strip()
        migrated = "\n".join(
            [
                f"## {entry_id} — {title}",
                "",
                "Status: active",
                f"Scope: {scope}",
                "Evidence:",
                "- legacy-unverified",
                "",
                *lines[1:],
            ]
        )
        updated.append(migrated)
        changed += 1
    parts = [preamble, *updated] if preamble else updated
    return (
        "\n\n".join(part for part in parts if part).rstrip() + "\n",
        changed,
        manual,
        tuple(generated_ids),
    )


def _migration_entry_seed(
    project_root: Path,
    memory_dir: Path,
    manifest: str,
) -> tuple[dict[str, str], Path | None]:
    sources: list[tuple[str, str]] = []
    decisions = memory_dir / "decisions.md"
    if decisions.exists():
        sources.append(("decisions.md", decisions.read_text(encoding="utf-8")))
    for relative in sorted(
        path for path in optional_index_paths(manifest)
        if path.startswith("areas/") and path.endswith(".md")
    ):
        path = memory_dir.joinpath(*Path(relative).parts)
        if path.exists():
            sources.append((relative, path.read_text(encoding="utf-8")))
    keys: list[str] = []
    fingerprint_parts = [digest_text(manifest)]
    for relative, text in sources:
        fingerprint_parts.extend([relative, digest_text(text)])
        _preamble, sections = split_h2(text)
        for index, section in enumerate(sections):
            if not ENTRY_ID_RE.search(section.splitlines()[0]) and "Decision:" in section:
                keys.append(_legacy_key(relative, section, index))
    source_sha = digest_text("\0".join(fingerprint_parts))
    return pending_entry_suffixes("migrate-entries", project_root, source_sha, keys)


def _build_plan(project_root: Path, memory_dir: Path) -> tuple[MutationPlan, list[str], tuple[Path, ...]]:
    manifest_path = memory_dir / "manifest.md"
    original = manifest_path.read_text(encoding="utf-8")
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
    if not project_id:
        project_id, seed_path = pending_project_id(
            "migrate",
            project_root,
            digest_text(original),
        )
    suffixes, entry_seed_path = _migration_entry_seed(project_root, memory_dir, original)
    # Supply the stable preview seed through metadata; the protocol helper preserves it.
    seeded = original
    if "project_id" not in metadata:
        marker = "## MemoryCustodian Protocol"
        if marker in seeded:
            seeded = seeded.replace(marker, marker + f"\n- project_id: {project_id}", 1)
        else:
            lines = seeded.splitlines()
            insert_at = next(
                (index for index, line in enumerate(lines) if line.startswith("## ")),
                len(lines),
            )
            lines[insert_at:insert_at] = [
                "## MemoryCustodian Protocol",
                f"- project_id: {project_id}",
                "",
            ]
            seeded = "\n".join(lines).rstrip() + "\n"
    routed, optional_routes_changed, legacy_optional_count = manifest_with_protocol_07_optional_routes(seeded)
    updated, metadata_changed = manifest_with_current_protocol_metadata(routed)
    updated, routing_changed = manifest_with_current_task_routing(updated)
    updated, index_changed = manifest_with_optional_index(updated)
    protocol_contract_metadata(updated)
    mutations: list[TextMutation] = []
    changes: list[str] = []
    if updated != original:
        mutations.append(TextMutation(manifest_path, updated))
    if metadata_changed or updated != original:
        changes.append("manifest.md: upgrade protocol metadata to 0.7 and preserve/generate project_id")
    if routing_changed:
        changes.append("manifest.md: load decisions.md for implementation, execution, and debugging")
    if index_changed:
        changes.append("manifest.md: add optional module index")
    if optional_routes_changed and legacy_optional_count:
        changes.append("manifest.md: preserve legacy optional descriptions with explicit-only activation")

    subjects_path = memory_dir / "subjects.md"
    if not subjects_path.exists():
        mutations.append(TextMutation(subjects_path, render_template("subjects.md", today())))
        changes.append("subjects.md: create managed Subject registry scaffold")

    decisions_path = memory_dir / "decisions.md"
    manual_reports: list[str] = []
    migrated_count = 0
    if decisions_path.exists():
        decisions = decisions_path.read_text(encoding="utf-8")
        migrated, migrated_count, manual, generated = _migrate_decisions(decisions, suffixes)
        if migrated != decisions:
            mutations.append(TextMutation(decisions_path, migrated))
            changes.append(f"decisions.md: add stable IDs and legacy-unverified Evidence to {migrated_count} structured entries")
            changes.extend(f"decisions.md: generated Entry ID {entry_id}" for entry_id in generated)
        if manual:
            manual_reports.append(f"{manual} ambiguous decisions.md H2 section(s)")

    for relative in sorted(
        path for path in optional_index_paths(original)
        if path.startswith("areas/") and path.endswith(".md")
    ):
        area_path = memory_dir.joinpath(*Path(relative).parts)
        if not area_path.exists():
            continue
        slug = Path(relative).stem
        area_original = area_path.read_text(encoding="utf-8")
        area_updated, area_count, area_manual, area_generated = _migrate_decisions(
            area_original,
            suffixes,
            relative,
            scope=f"area:{slug}",
            code="AREA",
        )
        if area_updated != area_original:
            mutations.append(TextMutation(area_path, area_updated))
            changes.append(
                f"{relative}: add stable area IDs and legacy-unverified Evidence to {area_count} structured entries"
            )
            changes.extend(f"{relative}: generated Entry ID {entry_id}" for entry_id in area_generated)
        if area_manual:
            manual_reports.append(f"{area_manual} ambiguous {relative} H2 section(s)")

    changelog = memory_dir / "changelog.md"
    if changelog.exists() and mutations:
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(
                    changelog.read_text(encoding="utf-8"),
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
        print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
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
