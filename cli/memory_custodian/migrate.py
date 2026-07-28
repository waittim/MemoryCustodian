"""Conservative, preview-first Protocol 0.5 to 0.6 migration."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import uuid

from .entries import ENTRY_ID_RE, split_h2
from .locking import mutation_lock
from .mutations import TextMutation, apply_mutations
from .plans import MutationPlan, print_plan
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    changelog_text,
    compare_versions,
    manifest_with_current_protocol_metadata,
    manifest_with_current_task_routing,
    manifest_with_optional_index,
    project_id_from_manifest,
    protocol_metadata,
    resolve_memory_dir,
    resolve_project_root,
)


def _stable_uuid4(seed: str) -> str:
    raw = bytearray(hashlib.sha256(seed.encode("utf-8")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def _legacy_id(project_id: str, relative: str, section: str, index: int) -> str:
    digest = hashlib.sha256(f"{project_id}\0{relative}\0{index}\0{section}".encode("utf-8")).hexdigest()[:8]
    date_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", section.splitlines()[0])
    stamp = "".join(date_match.groups()) if date_match else "19700101"
    return f"MC-DEC-{stamp}-{digest}"


def _migrate_decisions(text: str, project_id: str, relative: str = "decisions.md") -> tuple[str, int, int]:
    preamble, sections = split_h2(text)
    changed = 0
    manual = 0
    updated = []
    for index, section in enumerate(sections):
        if ENTRY_ID_RE.search(section.splitlines()[0]):
            updated.append(section)
            continue
        if "Decision:" not in section:
            manual += 1
            updated.append(section)
            continue
        entry_id = _legacy_id(project_id, relative, section, index)
        lines = section.splitlines()
        title = re.sub(r"^##\s+(?:\d{4}-\d{2}-\d{2}\s+-\s+)?", "", lines[0]).strip()
        migrated = "\n".join(
            [
                f"## {entry_id} — {title}",
                "",
                "Status: active",
                "Scope: project",
                "Evidence:",
                "- legacy-unverified",
                "",
                *lines[1:],
            ]
        )
        updated.append(migrated)
        changed += 1
    parts = [preamble, *updated] if preamble else updated
    return "\n\n".join(part for part in parts if part).rstrip() + "\n", changed, manual


def _build_plan(project_root: Path, memory_dir: Path) -> tuple[MutationPlan, list[str]]:
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
    project_id = metadata.get("project_id") or _stable_uuid4(original)
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
    updated, metadata_changed = manifest_with_current_protocol_metadata(seeded)
    updated, routing_changed = manifest_with_current_task_routing(updated)
    updated, index_changed = manifest_with_optional_index(updated)
    mutations: list[TextMutation] = []
    changes: list[str] = []
    if updated != original:
        mutations.append(TextMutation(manifest_path, updated))
    if metadata_changed or updated != original:
        changes.append("manifest.md: upgrade protocol metadata to 0.6 and preserve/generate project_id")
    if routing_changed:
        changes.append("manifest.md: load decisions.md for implementation, execution, and debugging")
    if index_changed:
        changes.append("manifest.md: add optional module index")

    decisions_path = memory_dir / "decisions.md"
    manual = 0
    migrated_count = 0
    if decisions_path.exists():
        decisions = decisions_path.read_text(encoding="utf-8")
        migrated, migrated_count, manual = _migrate_decisions(decisions, project_id)
        if migrated != decisions:
            mutations.append(TextMutation(decisions_path, migrated))
            changes.append(f"decisions.md: add stable IDs and legacy-unverified Evidence to {migrated_count} structured entries")

    changelog = memory_dir / "changelog.md"
    if changelog.exists() and mutations:
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(
                    changelog.read_text(encoding="utf-8"),
                    "Migrated project memory to Protocol 0.6 without rewriting legacy freeform units.",
                ),
            )
        )
    warnings = []
    if manual:
        warnings.append(f"Manual migration recommended for {manual} ambiguous decisions.md H2 section(s).")
    warnings.append("Legacy top-level bullets remain readable and are not mechanically rewritten.")
    return (
        MutationPlan(
            "migrate",
            {"memory_dir": str(memory_dir)},
            project_id,
            CURRENT_PROTOCOL_VERSION,
            tuple(mutations),
            tuple(warnings),
        ),
        changes,
    )


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest_path = memory_dir / "manifest.md"
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory missing: {memory_dir}")
    if not manifest_path.exists():
        raise ValueError(f"manifest.md missing: {manifest_path}")

    plan, changes = _build_plan(project_root, memory_dir)
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
        raise ValueError("Protocol 0.6 migration apply requires --confirm-plan <PLAN_ID>.")

    with mutation_lock(
        plan.project_id, project_root, "migrate",
        timeout=args.lock_timeout, break_stale=args.break_stale_lock,
    ):
        current, _changes = _build_plan(project_root, memory_dir)
        if current.plan_id != args.confirm_plan:
            print_plan(current)
            raise ValueError(
                f"Stale or mismatched plan: confirmed {args.confirm_plan}, current Plan ID is {current.plan_id}. No files written."
            )
        apply_mutations(list(current.mutations))
    print("Applied migration. Written files:")
    for mutation in current.mutations:
        print(f"- {mutation.path}")
    return 0
