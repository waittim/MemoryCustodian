"""Compact deterministic inbox entries."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re

from .markdown import MarkdownUnitRange, semantic_unit_ranges

from .protocol import (
    DECISION_ENTRY_BUDGET,
    budget_for,
    budget_state,
    changelog_text,
    estimate_tokens,
    long_decision_entries,
    parse_markdown_units,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
    split_top_level_bullet_units,
    today,
)
from .mutations import TextMutation, apply_mutations
from .locking import project_mutation_guard
from .plans import MutationPlan, print_plan
from .templates import render_template
from .entries import parse_structured_entries
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    manifest_contract_metadata,
)

ARCHIVABLE_H2_TARGETS = {"decisions.md", "changelog.md"}
BULLET_DEDUPE_TARGETS = {"constraints.md", "preferences.md"}
MANUAL_TARGET_REASONS = {
    "brief.md": "brief.md is the current one-screen summary; rewrite it semantically instead of archiving old lines.",
    "do-not-use.md": "do-not-use.md tombstones remain active; consolidate or shorten them instead of archiving them away.",
}


def _compact_plan(
    args,
    project_root: Path,
    memory_dir: Path,
    mutations: list[TextMutation],
) -> MutationPlan:
    manifest = read_managed_text(memory_dir, memory_dir / "manifest.md")
    metadata = manifest_contract_metadata(
        manifest,
        allow_missing_section=True,
    )
    comparison = compare_versions(
        metadata.get("protocol_version", "0.5"),
        CURRENT_PROTOCOL_VERSION,
    )
    if comparison is None:
        raise ValueError("Project manifest has an invalid protocol version.")
    if comparison > 0:
        raise ValueError("Project protocol is newer than this CLI supports.")
    protocol_06 = comparison == 0
    project_id = metadata["project_id"] if protocol_06 else "legacy-protocol-0.5"
    return MutationPlan(
        "compact",
        {"target": args.target or "inbox.md", "archive_oldest": args.archive_oldest},
        project_id or "legacy-protocol-0.5",
        metadata.get("protocol_version", "0.5"),
        tuple(mutations),
        project_root=project_root,
    )


def _execute_plan(
    args,
    project_root: Path,
    memory_dir: Path,
    mutations: list[TextMutation],
    rebuild,
) -> bool:
    plan = _compact_plan(args, project_root, memory_dir, mutations)
    protocol_06 = plan.protocol_version == CURRENT_PROTOCOL_VERSION
    project_id = plan.project_id
    print_plan(plan)
    if not args.apply:
        print("Dry run only. Re-run with --apply" + (" --confirm-plan <PLAN_ID>." if protocol_06 else "."))
        return False
    if protocol_06 and not args.confirm_plan:
        raise ValueError("Protocol 0.7 compact apply requires --confirm-plan <PLAN_ID>.")
    with project_mutation_guard(
        project_root,
        memory_dir / "manifest.md",
        "compact",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
        allow_legacy=True,
    ) as guard:
        current_mutations = rebuild()
        current_plan = _compact_plan(
            args,
            project_root,
            memory_dir,
            current_mutations,
        )
        current_comparison = compare_versions(
            current_plan.protocol_version,
            CURRENT_PROTOCOL_VERSION,
        )
        if current_comparison is None:
            raise ValueError(
                "Project protocol became invalid before compact apply."
            )
        if protocol_06:
            if guard.project_id != project_id:
                raise ValueError(
                    "Project identity changed before compact apply; preview again."
                )
            if current_plan.plan_id != args.confirm_plan:
                print_plan(current_plan)
                raise ValueError(
                    f"Stale or mismatched plan: confirmed {args.confirm_plan}, "
                    f"current Plan ID is {current_plan.plan_id}. No files written."
                )
        elif current_comparison == 0:
            raise ValueError(
                "Project migrated to Protocol 0.7 before compatibility compact apply; "
                "preview again and confirm the new Plan ID."
            )
        elif current_comparison > 0:
            raise ValueError(
                "Project protocol became newer than this CLI supports before "
                "compatibility compact apply; update MemoryCustodian."
            )
        else:
            print(
                "Migration available: Protocol 0.5 apply keeps legacy confirmation "
                "behavior under the bootstrap mutation guard."
            )
        apply_mutations(current_mutations)
        mutations = current_mutations
    print("Written files:")
    for mutation in mutations:
        print(f"- {mutation.path}")
    return True


def _dedupe_mutations(memory_dir: Path, target: str, path: Path) -> list[TextMutation]:
    original = read_managed_text(memory_dir, path)
    deduped, removed = _dedupe_bullets(original)
    if not removed:
        return []
    mutations = [TextMutation(path, deduped)]
    changelog = memory_dir / "changelog.md"
    if changelog.exists() and changelog != path:
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(
                    read_managed_text(memory_dir, changelog),
                    f"Compacted {target}: removed {removed} duplicate bullet(s).",
                ),
            )
        )
    return mutations


def _planned_archive_mutations(memory_dir: Path, target: str, budget: int) -> list[TextMutation]:
    path = memory_dir.joinpath(*PurePosixPath(target).parts)
    original = read_managed_text(memory_dir, path)
    plan = _plan_h2_archive(original, budget, target)
    if plan is None:
        return []
    mutations = _archive_mutations(memory_dir, target, plan["archived"])
    mutations.append(TextMutation(path, plan["compacted"]))
    changelog = memory_dir / "changelog.md"
    if target != "changelog.md" and changelog.exists():
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(
                    read_managed_text(memory_dir, changelog),
                    f"Compacted {target}: archived {len(plan['archived'])} old entries.",
                ),
            )
        )
    return mutations


def _inbox_cleanup_mutations(memory_dir: Path) -> list[TextMutation]:
    inbox = memory_dir / "inbox.md"
    original = read_managed_text(memory_dir, inbox)
    tombstone_path = memory_dir / "do-not-use.md"
    tombstones = read_managed_text(memory_dir, tombstone_path, required=False)
    cleaned, _candidates, duplicates, tombstone_matches = _clean_inbox(original, tombstones)
    if cleaned == original:
        return []
    mutations = [TextMutation(inbox, cleaned)]
    changelog = memory_dir / "changelog.md"
    if changelog.exists():
        message = (
            f"Cleaned inbox: removed {duplicates} exact duplicate(s) "
            f"and {tombstone_matches} exact tombstone match(es)."
        )
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(read_managed_text(memory_dir, changelog), message),
            )
        )
    return mutations


def _bullet_key(text: str) -> str:
    lines = text.rstrip().splitlines()
    if not lines:
        return ""
    first = lines[0][2:].strip()
    normalized = [first, *(line.rstrip() for line in lines[1:])]
    return "\n".join(normalized).strip().casefold()


def _bullet_label(text: str) -> str:
    lines = text.splitlines()
    return lines[0][2:].strip() if lines else ""


def _render_chunks(chunks: list[tuple[str, str]]) -> str:
    return "\n\n".join(text for _kind, text in chunks).rstrip() + "\n"


def _clean_inbox(text: str, tombstones: str) -> tuple[str, list[str], int, int]:
    """Remove only exact duplicate bullets and exact bullets already in tombstones."""

    tombstone_keys = {
        _bullet_key(unit_text)
        for kind, unit_text in split_top_level_bullet_units(tombstones)
        if kind == "bullet" and _bullet_key(unit_text)
    }
    tombstone_keys.update(
        (
            unit.heading.split("Tombstone:", 1)[1].strip().casefold()
            if "Tombstone:" in unit.heading
            else unit.heading.split(":", 1)[1].strip().casefold()
        )
        for unit in parse_markdown_units(tombstones).units
        if unit.kind == "h2"
        and unit.heading is not None
        and (
            unit.heading.casefold().startswith("tombstone:")
            or " — tombstone:" in unit.heading.casefold()
        )
    )
    seen: set[str] = set()
    candidates: list[str] = []
    kept_chunks: list[tuple[str, str]] = []
    duplicates = 0
    tombstone_matches = 0
    for kind, unit_text in split_top_level_bullet_units(text):
        if kind != "bullet":
            kept_chunks.append((kind, unit_text))
            continue
        key = _bullet_key(unit_text)
        if not key:
            kept_chunks.append((kind, unit_text))
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if key in tombstone_keys:
            tombstone_matches += 1
            continue
        candidates.append(unit_text)
        kept_chunks.append((kind, unit_text))
    if duplicates == 0 and tombstone_matches == 0:
        return text, candidates, 0, 0
    return _render_chunks(kept_chunks), candidates, duplicates, tombstone_matches


def _normalize_target(target: str) -> str:
    normalized = target.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Target must be a memory file path under docs/memory, such as decisions.md.")
    if not normalized.endswith(".md"):
        raise ValueError("Target must be a Markdown memory file.")
    if normalized == "manifest.md":
        raise ValueError("manifest.md defines loading policy and is not compacted by this command.")
    if normalized == "inbox.md":
        raise ValueError("Use `memory-custodian compact` without --target to compact inbox.md.")
    if normalized.startswith("archive/"):
        raise ValueError("archive/ is explicit-only and is not compacted by this command.")
    if budget_for(normalized) is None:
        raise ValueError(f"{normalized} has no context budget to compact against.")
    return normalized


def _target_path(memory_dir: Path, target: str) -> tuple[str, Path]:
    normalized = _normalize_target(target)
    return normalized, memory_dir.joinpath(*PurePosixPath(normalized).parts)


def _dedupe_bullets(text: str) -> tuple[str, int]:
    seen: set[str] = set()
    removed = 0
    kept: list[tuple[str, str]] = []
    for kind, unit_text in split_top_level_bullet_units(text):
        if kind == "bullet":
            key = _bullet_key(unit_text)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        kept.append((kind, unit_text))
    return _render_chunks(kept), removed


def _archivable_h2_ranges(
    ranges: tuple[MarkdownUnitRange, ...],
    target: str,
) -> list[MarkdownUnitRange]:
    """Attach changelog bullets to date H2s without swallowing legacy units elsewhere."""

    grouped = []
    for position, unit_range in enumerate(ranges):
        if unit_range.kind != "h2":
            continue
        end = unit_range.end
        if (
            target == "changelog.md"
            and unit_range.heading
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", unit_range.heading)
        ):
            following = position + 1
            while following < len(ranges) and ranges[following].kind == "bullet":
                end = ranges[following].end
                following += 1
        grouped.append(
            MarkdownUnitRange(
                unit_range.start,
                end,
                unit_range.kind,
                unit_range.heading,
            )
        )
    return grouped


def _join_h2_sections(preamble: list[str], sections: list[list[str]]) -> str:
    parts: list[str] = []
    preamble_text = "\n".join(preamble).rstrip()
    if preamble_text:
        parts.append(preamble_text)
    parts.extend("\n".join(section).strip() for section in sections)
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def _plan_h2_archive(text: str, budget: int, target: str = "decisions.md"):
    lines = text.rstrip().splitlines()
    ranges = semantic_unit_ranges(
        "\n".join(lines),
        start=1 if lines and lines[0].startswith("# ") else 0,
    )
    h2_ranges = _archivable_h2_ranges(ranges, target)
    if len(h2_ranges) < 2:
        return None

    for keep_count in range(len(h2_ranges) - 1, 0, -1):
        kept_ranges = h2_ranges[:keep_count]
        archived_ranges = h2_ranges[keep_count:]
        removed_lines = {
            index
            for unit_range in archived_ranges
            for index in range(unit_range.start, unit_range.end)
        }
        compacted = "\n".join(
            line for index, line in enumerate(lines) if index not in removed_lines
        ).rstrip() + "\n"
        projected = estimate_tokens(compacted)
        if projected <= budget:
            return {
                "compacted": compacted,
                "archived": [lines[item.start:item.end] for item in archived_ranges],
                "kept": [lines[item.start:item.end] for item in kept_ranges],
                "projected": projected,
            }
    return None


def _archive_target_path(memory_dir: Path, target: str) -> Path:
    stem = target[:-3].replace("/", "-")
    return memory_dir / "archive" / f"{stem}-{today()}.md"


def _is_legacy_archive_wrapper(section: list[str], target: str) -> bool:
    heading = section[0] if section else ""
    return heading.endswith(f" - From {target}") and any(
        line.strip() == "Reason:" for line in section[1:]
    )


def _merge_changelog_sections(sections: list[list[str]]) -> list[list[str]]:
    merged: dict[str, list[str]] = {}
    order: list[str] = []
    for section in sections:
        heading = section[0].strip()
        if heading not in merged:
            merged[heading] = list(section)
            order.append(heading)
            continue
        body = list(section[1:])
        while body and not body[0].strip():
            body.pop(0)
        if body:
            if merged[heading] and merged[heading][-1].strip():
                merged[heading].append("")
            merged[heading].extend(body)

    dated = all(
        len(heading) == len("## 2000-01-01")
        and heading.startswith("## ")
        and heading[3:7].isdigit()
        for heading in order
    )
    if dated:
        order.sort(key=lambda heading: heading[3:], reverse=True)
    return [merged[heading] for heading in order]


def _render_archive_document(
    target: str,
    existing: str,
    archived_sections: list[list[str]],
) -> str:
    standard_preamble = _archive_preamble(target)
    existing_body = existing
    if existing_body.startswith(standard_preamble):
        existing_body = existing_body[len(standard_preamble):].lstrip("\n")
    else:
        existing_lines_with_header = existing_body.splitlines()
        if (
            existing_lines_with_header
            and existing_lines_with_header[0].strip()
            == f"# Archived Memory: {target}"
        ):
            existing_body = "\n".join(existing_lines_with_header[1:]).lstrip("\n")
    existing_ranges = semantic_unit_ranges(existing_body)
    grouped_ranges = _archivable_h2_ranges(existing_ranges, target)
    existing_lines = existing_body.rstrip().splitlines()
    existing_sections = [
        existing_lines[unit_range.start:unit_range.end]
        for unit_range in grouped_ranges
    ]
    retained = [
        section
        for section in existing_sections
        if not _is_legacy_archive_wrapper(section, target)
    ]
    if target != "changelog.md":
        wrapper_ranges = [
            unit_range
            for unit_range, section in zip(grouped_ranges, existing_sections)
            if _is_legacy_archive_wrapper(section, target)
        ]
        removed = {
            index
            for unit_range in wrapper_ranges
            for index in range(unit_range.start, unit_range.end)
        }
        base_lines = [
            line for index, line in enumerate(existing_lines) if index not in removed
        ]
        retained_ranges = [
            unit_range
            for unit_range, section in zip(grouped_ranges, existing_sections)
            if not _is_legacy_archive_wrapper(section, target)
        ]
        first_h2 = retained_ranges[0].start if retained_ranges else len(existing_lines)
        insertion = sum(1 for index in range(first_h2) if index not in removed)
        new_lines = _join_h2_sections([], archived_sections).rstrip().splitlines()
        if new_lines:
            before = base_lines[:insertion]
            after = base_lines[insertion:]
            if before and before[-1].strip():
                before.append("")
            if after and new_lines[-1].strip():
                new_lines.append("")
            body = "\n".join([*before, *new_lines, *after]).strip()
        else:
            body = "\n".join(base_lines).strip()
        rendered = _archive_preamble(target).rstrip()
        if body:
            rendered += "\n\n" + body
        return rendered.rstrip() + "\n"

    sections = [*archived_sections, *retained]
    sections = _merge_changelog_sections(sections)
    covered = {
        index
        for unit_range in grouped_ranges
        for index in range(unit_range.start, unit_range.end)
    }
    preserved = "\n".join(
        line
        for index, line in enumerate(existing_lines)
        if index not in covered
    ).strip()
    rendered = _join_h2_sections(_archive_preamble(target).rstrip().splitlines(), sections)
    if preserved:
        rendered = rendered.rstrip() + "\n\n" + preserved + "\n"
    return rendered


def _archive_preamble(target: str) -> str:
    lines = [
        f"# Archived Memory: {target}",
        "",
        "Complete historical entries moved from active memory after reviewed compaction.",
        "This file is explicit-only and is not part of normal task context.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _archive_mutations(memory_dir: Path, target: str, archived_sections: list[list[str]]) -> list[TextMutation]:
    mutations: list[TextMutation] = []
    readme = memory_dir / "archive" / "README.md"
    if not readme.exists():
        mutations.append(TextMutation(readme, render_template("archive/README.md", today())))

    archive_path = _archive_target_path(memory_dir, target)
    existing = read_managed_text(memory_dir, archive_path, required=False)
    archive_text = _render_archive_document(target, existing, archived_sections)
    mutations.append(TextMutation(archive_path, archive_text))
    return mutations


def _print_long_decision_entries(entries: list[tuple[str, int]]) -> None:
    if not entries:
        return
    print(f"Long decision entries: {len(entries)} over {DECISION_ENTRY_BUDGET} tokens")
    for title, tokens in entries[:10]:
        print(f"- {title}: {tokens} tokens")
    if len(entries) > 10:
        print(f"- ... and {len(entries) - 10} more")


def _run_target_compaction(args, project_root: Path, memory_dir: Path) -> int:
    target, path = _target_path(memory_dir, args.target)
    if not path.exists():
        raise FileNotFoundError(f"Target not found: {path}")

    budget = budget_for(target)
    original = read_managed_text(memory_dir, path)
    tokens = estimate_tokens(original)
    long_entries = long_decision_entries(original)

    print("# Target Compaction Plan")
    print(f"Target: {target}")
    print(f"Current tokens: {tokens}/{budget} max")
    state = budget_state(tokens, budget)
    print(f"State: {state}")
    _print_long_decision_entries(long_entries)
    if tokens <= budget:
        if long_entries:
            print(
                "Manual review required: shorten long decisions semantically; "
                "move supporting detail to constraints, matched area context, or source documentation."
            )
        elif state == "NEAR LIMIT":
            print("Maintenance preview (dry run; no files changed):")
            if target == "decisions.md":
                print("- Shorten long entries, merge duplicates, link superseded decisions, and move scoped knowledge.")
                print("- Confirm active invariants remain reachable before considering age-based archival.")
            else:
                print("- Review duplicates, obsolete detail, and content that belongs in a scoped module.")
            print("Maintenance recommended before the next write.")
        else:
            print("Status: OK")
        return 0

    working = original
    applied_actions: list[str] = []
    if target in BULLET_DEDUPE_TARGETS:
        deduped, removed = _dedupe_bullets(working)
        if removed:
            working = deduped
            projected = estimate_tokens(working)
            print(f"Action: remove {removed} exact duplicate bullet(s)")
            print(f"Projected tokens after dedupe: {projected}/{budget} max")
            mutations = _dedupe_mutations(memory_dir, target, path)
            if projected <= budget:
                if _execute_plan(
                    args,
                    project_root,
                    memory_dir,
                    mutations,
                    lambda: _dedupe_mutations(memory_dir, target, path),
                ):
                    print("Applied target compaction.")
                return 0

    manual_reason = MANUAL_TARGET_REASONS.get(target)
    if manual_reason:
        print(f"Manual review required: {manual_reason}")
        if applied_actions:
            print("Applied partial deterministic compaction; target remains over budget.")
        elif not args.apply:
            print("Dry run only. No deterministic safe rewrite is available for this target.")
        return 0

    if target in ARCHIVABLE_H2_TARGETS:
        plan = _plan_h2_archive(working, budget, target)
        if plan is not None:
            archive_path = _archive_target_path(memory_dir, target).relative_to(memory_dir).as_posix()
            print("Action: archive oldest complete H2 entries")
            print(f"Keep entries: {len(plan['kept'])}")
            print(f"Archive entries: {len(plan['archived'])}")
            print(f"Archive path: {archive_path}")
            print(f"Projected tokens: {plan['projected']}/{budget} max")
            kept_long_entries: list[tuple[str, int]] = []
            if target == "decisions.md":
                kept_long_entries = long_decision_entries(plan["compacted"])
                if kept_long_entries:
                    print(
                        f"Kept long entries: {len(kept_long_entries)} still exceed "
                        f"{DECISION_ENTRY_BUDGET} tokens and require semantic shortening."
                    )
                print(
                    "Semantic review required: merge superseded entries and retain active invariants "
                    "in brief.md, constraints.md, or matched areas before archival."
                )
            mutations = _planned_archive_mutations(memory_dir, target, budget)
            if not args.apply:
                if target == "decisions.md":
                    print("After semantic review, confirm this plan with --apply --archive-oldest.")
                else:
                    print("Review this plan before applying.")
                _execute_plan(
                    args,
                    project_root,
                    memory_dir,
                    mutations,
                    lambda: _planned_archive_mutations(memory_dir, target, budget),
                )
                return 0
            if target == "decisions.md" and kept_long_entries:
                print("Not applied: shorten the kept long decisions before age-based archival.")
                return 1
            if target == "decisions.md" and not args.archive_oldest:
                print(
                    "Not applied: re-run with --archive-oldest only after confirming the oldest entries "
                    "contain no active invariant that would become unreachable."
                )
                return 1

            _execute_plan(
                args,
                project_root,
                memory_dir,
                mutations,
                lambda: _planned_archive_mutations(memory_dir, target, budget),
            )
            print("Applied target compaction.")
            return 0

    if applied_actions:
        print("Applied partial deterministic compaction; target remains over budget.")
    else:
        print("Manual review required: shorten, merge, split into optional modules, or archive content after semantic review.")
        if not args.apply:
            print("Dry run only. No deterministic safe rewrite is available for this target.")
    return 0


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory not found: {memory_dir}")
    if not (memory_dir / "manifest.md").exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    manifest_contract_metadata(
        read_managed_text(memory_dir, memory_dir / "manifest.md"),
        allow_missing_section=True,
    )
    if args.target:
        return _run_target_compaction(args, project_root, memory_dir)

    inbox = memory_dir / "inbox.md"
    if not inbox.exists():
        raise FileNotFoundError(f"Inbox not found: {inbox}")

    original = read_managed_text(memory_dir, inbox)
    tombstone_path = memory_dir / "do-not-use.md"
    tombstones = read_managed_text(memory_dir, tombstone_path, required=False)
    structured_candidates = [
        entry for entry in parse_structured_entries(inbox, original)
        if entry.status == "candidate"
    ]
    legacy_items = [
        unit_text
        for kind, unit_text in split_top_level_bullet_units(original)
        if kind == "bullet"
    ]
    cleaned, legacy_candidates, duplicates, tombstone_matches = _clean_inbox(original, tombstones)
    review_items = [
        *(("structured", entry.text, entry) for entry in structured_candidates),
        *(("legacy", item, None) for item in legacy_candidates),
    ]
    items = [entry.text for entry in structured_candidates] + legacy_items

    print("# Compaction Plan")
    print(f"Inbox items: {len(items)}")
    print(f"Exact duplicates removable: {duplicates}")
    print(f"Exact tombstone matches removable: {tombstone_matches}")
    print(f"Candidates requiring Agent review: {len(review_items)}")
    for index, (kind, item, entry) in enumerate(review_items, start=1):
        if kind == "structured" and entry is not None:
            print(f"- [{index}] {entry.entry_id} — {entry.title}")
            continue
        lines = item.splitlines()
        print(f"- [{index}] {_bullet_label(item)}")
        for line in lines[1:]:
            print(f"      {line}")
    print("No semantic destinations are inferred. Review scope, type, confidence, and existing memory before using `add` or editing Markdown.")

    if cleaned == original:
        print("No deterministic inbox changes to apply; candidates remain for Agent review.")
        return 0

    mutations = _inbox_cleanup_mutations(memory_dir)
    applied = _execute_plan(
        args,
        project_root,
        memory_dir,
        mutations,
        lambda: _inbox_cleanup_mutations(memory_dir),
    )
    if not applied:
        return 0
    if review_items:
        print("Applied deterministic inbox cleanup; candidates remain for Agent review.")
    else:
        print("Applied deterministic inbox cleanup; no candidates remain.")
    return 0
