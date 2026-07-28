"""Compact deterministic inbox entries."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from .protocol import (
    DECISION_ENTRY_BUDGET,
    appended_text,
    budget_for,
    changelog_text,
    estimate_tokens,
    long_decision_entries,
    parse_markdown_units,
    resolve_memory_dir,
    resolve_project_root,
    split_top_level_bullet_units,
    today,
)
from .mutations import TextMutation, apply_mutations
from .locking import mutation_lock
from .plans import MutationPlan, print_plan
from .templates import render_template
from .entries import parse_structured_entries
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    project_id_from_manifest,
    protocol_metadata,
)

ARCHIVABLE_H2_TARGETS = {"decisions.md", "changelog.md"}
BULLET_DEDUPE_TARGETS = {"constraints.md", "preferences.md"}
MANUAL_TARGET_REASONS = {
    "brief.md": "brief.md is the current one-screen summary; rewrite it semantically instead of archiving old lines.",
    "do-not-use.md": "do-not-use.md tombstones remain active; consolidate or shorten them instead of archiving them away.",
}


def _execute_plan(args, project_root: Path, memory_dir: Path, mutations: list[TextMutation], label: str) -> bool:
    manifest = (memory_dir / "manifest.md").read_text(encoding="utf-8")
    metadata = protocol_metadata(manifest)
    protocol_06 = compare_versions(metadata.get("protocol_version", "0.5"), CURRENT_PROTOCOL_VERSION) == 0
    project_id = project_id_from_manifest(manifest) if protocol_06 else "legacy-protocol-0.5"
    plan = MutationPlan(
        "compact",
        {"target": args.target or "inbox.md", "archive_oldest": args.archive_oldest},
        project_id or "legacy-protocol-0.5",
        metadata.get("protocol_version", "0.5"),
        tuple(mutations),
    )
    print_plan(plan)
    if not args.apply:
        print("Dry run only. Re-run with --apply" + (" --confirm-plan <PLAN_ID>." if protocol_06 else "."))
        return False
    if protocol_06:
        if not args.confirm_plan:
            raise ValueError("Protocol 0.6 compact apply requires --confirm-plan <PLAN_ID>.")
        with mutation_lock(
            project_id, project_root, "compact",
            timeout=args.lock_timeout, break_stale=args.break_stale_lock,
        ):
            current_id = plan.plan_id
            if current_id != args.confirm_plan:
                print_plan(plan)
                raise ValueError(
                    f"Stale or mismatched plan: confirmed {args.confirm_plan}, current Plan ID is {current_id}. No files written."
                )
            apply_mutations(mutations)
    else:
        print("Migration available: Protocol 0.5 apply keeps legacy confirmation behavior.")
        apply_mutations(mutations)
    print("Written files:")
    for mutation in mutations:
        print(f"- {mutation.path}")
    return True


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
    return "\n".join(text for _kind, text in chunks).rstrip() + "\n"


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


def _split_h2_sections(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.rstrip().splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if not starts:
        return lines, []

    preamble = lines[: starts[0]]
    sections: list[list[str]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        sections.append(lines[start:end])
    return preamble, sections


def _join_h2_sections(preamble: list[str], sections: list[list[str]]) -> str:
    parts: list[str] = []
    preamble_text = "\n".join(preamble).rstrip()
    if preamble_text:
        parts.append(preamble_text)
    parts.extend("\n".join(section).strip() for section in sections)
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def _plan_h2_archive(text: str, budget: int):
    preamble, sections = _split_h2_sections(text)
    if len(sections) < 2:
        return None

    for keep_count in range(len(sections) - 1, 0, -1):
        kept = sections[:keep_count]
        archived = sections[keep_count:]
        compacted = _join_h2_sections(preamble, kept)
        projected = estimate_tokens(compacted)
        if projected <= budget:
            return {
                "compacted": compacted,
                "archived": archived,
                "kept": kept,
                "projected": projected,
            }
    return None


def _archive_target_path(memory_dir: Path, target: str) -> Path:
    stem = target[:-3].replace("/", "-")
    return memory_dir / "archive" / f"{stem}-{today()}.md"


def _archive_mutations(memory_dir: Path, target: str, archived_sections: list[list[str]]) -> list[TextMutation]:
    mutations: list[TextMutation] = []
    readme = memory_dir / "archive" / "README.md"
    if not readme.exists():
        mutations.append(TextMutation(readme, render_template("archive/README.md", today())))

    archive_path = _archive_target_path(memory_dir, target)
    body = (
        f"## {today()} - From {target}\n"
        "Reason:\n"
        "Active memory exceeded its context budget; older complete entries were moved to explicit-only archive.\n\n"
        + "\n\n".join("\n".join(section).strip() for section in archived_sections)
    )
    if archive_path.exists():
        archive_text = appended_text(archive_path.read_text(encoding="utf-8"), body)
    else:
        archive_text = f"# Archived Memory: {target}\n\n{body}\n"
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
    original = path.read_text(encoding="utf-8")
    tokens = estimate_tokens(original)
    long_entries = long_decision_entries(original)

    print("# Target Compaction Plan")
    print(f"Target: {target}")
    print(f"Current tokens: {tokens}/{budget} max")
    _print_long_decision_entries(long_entries)
    if tokens <= budget:
        if long_entries:
            print(
                "Manual review required: shorten long decisions semantically; "
                "move supporting detail to constraints, matched area context, or source documentation."
            )
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
            mutations = [TextMutation(path, working)]
            changelog = memory_dir / "changelog.md"
            if changelog.exists() and changelog != path:
                mutations.append(
                    TextMutation(
                        changelog,
                        changelog_text(
                            changelog.read_text(encoding="utf-8"),
                            f"Compacted {target}: removed {removed} duplicate bullet(s).",
                        ),
                    )
                )
            if projected <= budget:
                if _execute_plan(args, project_root, memory_dir, mutations, "dedupe"):
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
        plan = _plan_h2_archive(working, budget)
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
            mutations = _archive_mutations(memory_dir, target, plan["archived"])
            mutations.append(TextMutation(path, plan["compacted"]))
            changelog = memory_dir / "changelog.md"
            if target != "changelog.md" and changelog.exists():
                mutations.append(
                    TextMutation(
                        changelog,
                        changelog_text(
                            changelog.read_text(encoding="utf-8"),
                            f"Compacted {target}: archived {len(plan['archived'])} old entries.",
                        ),
                    )
                )
            if not args.apply:
                if target == "decisions.md":
                    print("After semantic review, confirm this plan with --apply --archive-oldest.")
                else:
                    print("Review this plan before applying.")
                _execute_plan(args, project_root, memory_dir, mutations, "archive")
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

            _execute_plan(args, project_root, memory_dir, mutations, "archive")
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
    if args.target:
        return _run_target_compaction(args, project_root, memory_dir)

    inbox = memory_dir / "inbox.md"
    if not inbox.exists():
        raise FileNotFoundError(f"Inbox not found: {inbox}")

    original = inbox.read_text(encoding="utf-8")
    tombstone_path = memory_dir / "do-not-use.md"
    tombstones = tombstone_path.read_text(encoding="utf-8") if tombstone_path.exists() else ""
    structured_candidates = [
        entry for entry in parse_structured_entries(inbox, original)
        if entry.status == "candidate"
    ]
    if structured_candidates:
        items = [entry.text for entry in structured_candidates]
        cleaned, candidates, duplicates, tombstone_matches = original, items, 0, 0
    else:
        items = [unit_text for kind, unit_text in split_top_level_bullet_units(original) if kind == "bullet"]
        cleaned, candidates, duplicates, tombstone_matches = _clean_inbox(original, tombstones)

    print("# Compaction Plan")
    print(f"Inbox items: {len(items)}")
    print(f"Exact duplicates removable: {duplicates}")
    print(f"Exact tombstone matches removable: {tombstone_matches}")
    print(f"Candidates requiring Agent review: {len(candidates)}")
    for index, item in enumerate(candidates, start=1):
        if structured_candidates:
            entry = structured_candidates[index - 1]
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

    mutations = [TextMutation(inbox, cleaned)]
    changelog = memory_dir / "changelog.md"
    if changelog.exists():
        message = f"Cleaned inbox: removed {duplicates} exact duplicate(s) and {tombstone_matches} exact tombstone match(es)."
        mutations.append(TextMutation(changelog, changelog_text(changelog.read_text(encoding="utf-8"), message)))
    applied = _execute_plan(args, project_root, memory_dir, mutations, "inbox-cleanup")
    if not applied:
        return 0
    if candidates:
        print("Applied deterministic inbox cleanup; candidates remain for Agent review.")
    else:
        print("Applied deterministic inbox cleanup; no candidates remain.")
    return 0
