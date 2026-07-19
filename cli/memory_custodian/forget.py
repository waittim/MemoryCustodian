"""Preview and apply structure-safe memory forgetting plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .protocol import (
    MarkdownUnit,
    ensure_newline,
    iter_markdown_files,
    optional_index_paths,
    parse_markdown_units,
    read_text,
    render_markdown_document,
    resolve_memory_dir,
    resolve_project_root,
    today,
    write_text,
)


@dataclass(frozen=True)
class FilePlan:
    path: Path
    updated: str
    matches: tuple[MarkdownUnit, ...]
    blockers: tuple[MarkdownUnit, ...]


def _target_files(memory_dir: Path, mode: str) -> list[Path]:
    excluded = {"manifest.md", "do-not-use.md"}
    if mode == "purge":
        candidates = iter_markdown_files(memory_dir, include_archive=True)
        return sorted(
            {path for path in candidates if path.name != "README.md" and path.relative_to(memory_dir).as_posix() not in excluded}
        )

    manifest = read_text(memory_dir / "manifest.md")
    enabled = optional_index_paths(manifest)
    active_core = {"brief.md", "decisions.md", "constraints.md", "preferences.md", "inbox.md", "changelog.md"}
    candidates: set[Path] = set()
    for path in iter_markdown_files(memory_dir, include_archive=False):
        relative = path.relative_to(memory_dir).as_posix()
        if relative in active_core or relative in enabled:
            candidates.add(path)
    return sorted(path for path in candidates if path.name != "README.md" and path.name != "do-not-use.md")


def _remove_units(text: str, topic: str) -> tuple[str, tuple[MarkdownUnit, ...], tuple[MarkdownUnit, ...]]:
    document = parse_markdown_units(text)
    needle = topic.casefold()
    matches = tuple(
        unit
        for unit in document.units
        if unit.kind in {"h2", "bullet"}
        and needle in unit.text.casefold()
        and not (unit.kind == "h2" and len(unit.text.splitlines()) == 1)
    )
    blockers = tuple(
        unit for unit in document.units if unit.kind in {"preamble", "body"} and needle in unit.text.casefold()
    )
    kept = [unit for unit in document.units if unit not in matches]
    return render_markdown_document(document, kept), matches, blockers


def _prepend_entry(text: str, entry: str) -> str:
    document = parse_markdown_units(text)
    units = [MarkdownUnit("h2", entry.strip(), entry.splitlines()[0][3:].strip()), *document.units]
    return render_markdown_document(document, units)


def _append_changelog_entry(text: str, message: str) -> str:
    entry = f"## {today()}\n- {message}"
    if not text.strip():
        return f"# Memory Changelog\n\n{entry}\n"
    return _prepend_entry(text, entry)


def _tombstone(topic: str, mode: str) -> str | None:
    if mode == "purge":
        return None
    if mode == "hard":
        return (
            "## Tombstone: Redacted user-requested removal\n"
            "A user-requested topic was removed in hard mode. Do not reconstruct removed content from prior context "
            "unless the user explicitly reverses this request."
        )
    return (
        f"## Tombstone: {topic}\n"
        "Do not reintroduce unless the user explicitly reverses this. "
        f"Reason: the user asked MemoryCustodian to forget this topic. Mode: soft. Date: {today()}."
    )


def _update_existing_tombstones(text: str, topic: str, mode: str) -> tuple[str, tuple[MarkdownUnit, ...], tuple[MarkdownUnit, ...]]:
    document = parse_markdown_units(text)
    needle = topic.casefold()
    matches = tuple(
        unit
        for unit in document.units
        if unit.kind == "h2"
        and unit.heading is not None
        and unit.heading.casefold().startswith("tombstone:")
        and needle in unit.text.casefold()
    )
    blockers = tuple(
        unit
        for unit in document.units
        if needle in unit.text.casefold()
        and (
            unit.kind in {"preamble", "body"}
            or (unit.kind == "h2" and (unit.heading is None or not unit.heading.casefold().startswith("tombstone:")))
        )
    )
    kept = [unit for unit in document.units if unit not in matches]
    if mode == "hard":
        generic = _tombstone(topic, mode)
        if generic is not None and not any(unit.text.strip() == generic.strip() for unit in kept):
            kept.insert(0, MarkdownUnit("h2", generic.strip(), generic.splitlines()[0][3:].strip()))
    return render_markdown_document(document, kept), matches, blockers


def _summary(unit: MarkdownUnit, redact: bool, number: int) -> str:
    if redact:
        return "[redacted matching entry]" if unit.heading else f"entry {number}"
    if unit.heading:
        return unit.heading
    first = unit.text.splitlines()[0].lstrip("-*+ ").strip()
    return first[:100]


def run(args) -> int:
    topic = args.topic.strip()
    if not topic:
        raise ValueError("Forget topic must not be empty.")
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        return 1
    if not (memory_dir / "manifest.md").exists():
        raise ValueError("manifest.md is missing; forgetting cannot safely resolve active memory")
    if not (memory_dir / "do-not-use.md").exists():
        raise ValueError("do-not-use.md is missing; forgetting cannot safely record removal guards")

    targets = _target_files(memory_dir, args.mode)
    plans: list[FilePlan] = []
    for path in targets:
        original = read_text(path)
        updated, matches, blockers = _remove_units(original, topic)
        plans.append(FilePlan(path, updated, matches, blockers))

    matched_plans = [plan for plan in plans if plan.matches]
    total_matches = sum(len(plan.matches) for plan in plans)
    blocker_plans = [plan for plan in plans if plan.blockers]
    tombstone_matches: tuple[MarkdownUnit, ...] = ()
    tombstone_blockers: tuple[MarkdownUnit, ...] = ()
    tombstone_updated: str | None = None
    tombstone_path = memory_dir / "do-not-use.md"
    if args.mode in {"hard", "purge"}:
        tombstone_original = read_text(tombstone_path)
        candidate, tombstone_matches, tombstone_blockers = _update_existing_tombstones(
            tombstone_original, topic, args.mode
        )
        if candidate != ensure_newline(tombstone_original):
            tombstone_updated = candidate
    manual_blockers = sum(len(plan.blockers) for plan in plans) + len(tombstone_blockers)
    broad_reasons: list[str] = []
    if len("".join(topic.split())) < 4:
        broad_reasons.append("topic has fewer than four non-whitespace characters")
    if total_matches + len(tombstone_matches) + manual_blockers > 1:
        broad_reasons.append("plan matches more than one semantic unit")

    tombstone = _tombstone(topic, args.mode)
    changelog_path = memory_dir / "changelog.md"
    if args.mode == "soft" and tombstone:
        tombstone_updated = _prepend_entry(read_text(tombstone_path), tombstone)
    changelog_message = f"Forgot topic '{topic}' with mode soft." if args.mode == "soft" else f"Completed {args.mode} forget operation."
    changelog_plan = next((plan for plan in plans if plan.path == changelog_path), None)
    changelog_base = changelog_plan.updated if changelog_plan else (read_text(changelog_path) if changelog_path.exists() else "")
    changelog_updated = _append_changelog_entry(changelog_base, changelog_message) if changelog_path.exists() else None

    print(f"Mode: {args.mode}")
    print(f"Searched files: {len(targets)}")
    print(f"Matched files: {len(matched_plans)}")
    print(f"Matched units: {total_matches}")
    redact = args.mode in {"hard", "purge"}
    for plan in matched_plans:
        relative = plan.path.relative_to(memory_dir).as_posix()
        for number, unit in enumerate(plan.matches, start=1):
            print(f"- {relative}: {_summary(unit, redact, number)}")
    if tombstone_matches:
        print(f"Matched tombstones: {len(tombstone_matches)}")
    if args.mode == "hard" and tombstone_matches:
        print("Tombstone: replace matching topic-bearing guards with one generic redacted guard")
    elif args.mode == "hard":
        print("Tombstone: generic redacted guard")
    elif args.mode == "purge":
        print("Tombstone: remove matching topic-bearing guards")
    else:
        print("Tombstone: topic-bearing guard")
    print("Changelog: " + ("generic operation record" if changelog_updated and redact else "topic-bearing record" if changelog_updated else "not enabled"))
    print("Broad-match confirmation required: " + ("yes" if broad_reasons else "no"))
    if manual_blockers:
        print(f"Manual rewrite required: {manual_blockers} non-removable unit(s)")
        for plan in blocker_plans:
            relative = plan.path.relative_to(memory_dir).as_posix()
            for unit in plan.blockers:
                print(f"- {relative}: {unit.kind} contains matching content")
        for unit in tombstone_blockers:
            print(f"- do-not-use.md: {unit.kind} contains matching content")
    if args.mode == "purge":
        print("Warning: Git history, backups, caches, and external copies are outside this command's scope.")
    if not args.apply:
        if manual_blockers:
            print("Dry run only. Rewrite the listed content semantically, then preview again before applying.")
        else:
            print("Dry run only. Re-run with --apply.")
        return 0
    if manual_blockers:
        print("Refusing apply: rewrite the listed body/preamble content semantically, then preview again.")
        return 1
    if broad_reasons and not args.allow_broad_match:
        print("Refusing broad-risk apply: " + "; ".join(broad_reasons) + ". Re-run with --allow-broad-match after review.")
        return 1

    writes: list[tuple[Path, str]] = [
        (plan.path, plan.updated) for plan in matched_plans if plan.path != changelog_path
    ]
    if tombstone_updated is not None:
        writes.append((tombstone_path, tombstone_updated))
    if changelog_updated is not None:
        writes.append((changelog_path, changelog_updated))
    completed: list[str] = []
    try:
        for path, updated in writes:
            write_text(path, ensure_newline(updated))
            completed.append(path.relative_to(memory_dir).as_posix())
    except OSError as exc:
        print(f"Forget apply failed after writing {len(completed)} file(s): {exc}")
        if completed:
            print("Successfully written:")
            for name in completed:
                print(f"- {name}")
        return 1

    print(f"Applied forgetting plan. Written files: {len(completed)}")
    for name in completed:
        print(f"- {name}")
    return 0
