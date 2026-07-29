"""Preview and apply structure-safe memory forgetting plans."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import uuid

from .entries import parse_structured_entries
from .locking import project_mutation_guard
from .erasure import ErasureScope, render_apply_boundary, render_scope, scope_for_forget
from .mutations import TextMutation, apply_mutations
from .plans import (
    MutationPlan,
    digest_text,
    discard_pending_seed,
    pending_entry_suffixes,
    pending_plan_nonce,
    print_plan,
)
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    MarkdownUnit,
    compare_versions,
    ensure_newline,
    iter_markdown_files,
    optional_index_paths,
    parse_markdown_units,
    read_text,
    render_markdown_document,
    resolve_memory_dir,
    resolve_project_root,
    project_id_from_manifest,
    protocol_metadata,
    today,
)
from .subjects import SUBJECT_ID_RE


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


def _tombstone(
    topic: str,
    mode: str,
    project_id: str | None = None,
    tombstone_suffix: str | None = None,
) -> str | None:
    if mode == "purge":
        return None
    if project_id:
        stamp = today().replace("-", "")
        if mode == "hard":
            if tombstone_suffix is None:
                raise ValueError("Hard forget requires a random pending Tombstone ID seed.")
            suffix = tombstone_suffix
        else:
            suffix = hashlib.sha256(f"{project_id}\0{mode}\0{topic}".encode()).hexdigest()[:8]
        entry_id = f"MC-TOMB-{stamp}-{suffix}"
        title = "Redacted user-requested removal" if mode == "hard" else topic
        statement = (
            "A user-requested topic was removed in hard mode. Do not reconstruct removed content from prior context."
            if mode == "hard"
            else f"Do not reintroduce {topic} unless the user explicitly reverses this request."
        )
        return (
            f"## {entry_id} — Tombstone: {title}\n\n"
            "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
            f"Rejected:\n{statement}\n\nReason:\nUser-requested forgetting guard."
        )
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


def _update_existing_tombstones(
    text: str,
    topic: str,
    mode: str,
    project_id: str | None = None,
    tombstone_suffix: str | None = None,
) -> tuple[str, tuple[MarkdownUnit, ...], tuple[MarkdownUnit, ...]]:
    document = parse_markdown_units(text)
    needle = topic.casefold()
    matches = tuple(
        unit
        for unit in document.units
        if unit.kind == "h2"
        and unit.heading is not None
        and (
            unit.heading.casefold().startswith("tombstone:")
            or unit.heading.casefold().startswith("mc-tomb-")
        )
        and needle in unit.text.casefold()
    )
    blockers = tuple(
        unit
        for unit in document.units
        if needle in unit.text.casefold()
        and (
            unit.kind in {"preamble", "body"}
            or (
                unit.kind == "h2"
                and (
                    unit.heading is None
                    or not unit.heading.casefold().startswith(("tombstone:", "mc-tomb-"))
                )
            )
        )
    )
    kept = [unit for unit in document.units if unit not in matches]
    if mode == "hard":
        generic = _tombstone(topic, mode, project_id, tombstone_suffix)
        has_generic_guard = any(
            "Redacted user-requested removal" in unit.text
            and "Do not reconstruct removed content" in unit.text
            for unit in kept
        )
        if generic is not None and not has_generic_guard:
            kept.insert(0, MarkdownUnit("h2", generic.strip(), generic.splitlines()[0][3:].strip()))
    return render_markdown_document(document, kept), matches, blockers


def _summary(unit: MarkdownUnit, redact: bool, number: int) -> str:
    if redact:
        return "[redacted matching entry]" if unit.heading else f"entry {number}"
    if unit.heading:
        return unit.heading
    first = unit.text.splitlines()[0].lstrip("-*+ ").strip()
    return first[:100]


def _public_text(value: str, topic: str, redact: bool) -> str:
    if not redact:
        return value
    return re.sub(
        re.escape(topic),
        "[redacted]",
        value,
        flags=re.IGNORECASE,
    )


def _subject_reference_blockers(
    memory_dir: Path,
    plans: list[FilePlan],
    tombstone_updated: str | None,
) -> list[str]:
    registry_plan = next(
        (plan for plan in plans if plan.path.relative_to(memory_dir).as_posix() == "subjects.md"),
        None,
    )
    if registry_plan is None or not registry_plan.matches:
        return []
    removed_ids = {
        match.group(0).casefold()
        for unit in registry_plan.matches
        for match in SUBJECT_ID_RE.finditer(unit.text)
    }
    if not removed_ids:
        return []
    planned_text = {plan.path: plan.updated for plan in plans}
    if tombstone_updated is not None:
        planned_text[memory_dir / "do-not-use.md"] = tombstone_updated
    references: dict[str, list[str]] = {subject_id: [] for subject_id in removed_ids}
    for path in iter_markdown_files(memory_dir, include_archive=True):
        if path.name == "subjects.md":
            continue
        text = planned_text.get(path, read_text(path))
        for entry in parse_structured_entries(path, text):
            for field in ("Subject", "Provisional-Subject"):
                subject_id = entry.fields.get(field, "").casefold()
                if subject_id in references:
                    references[subject_id].append(
                        f"{path.relative_to(memory_dir).as_posix()}:{entry.entry_id}"
                    )
    return [
        f"subjects.md: cannot remove {subject_id.upper()} while referenced by {', '.join(owners)}"
        for subject_id, owners in references.items()
        if owners
    ]


def _build_forget_mutation_plan(
    args,
    project_root: Path,
    memory_dir: Path,
    project_id: str | None,
    protocol_version: str,
    tombstone_suffix: str | None = None,
    privacy_nonce: str | None = None,
) -> MutationPlan:
    topic = args.topic.strip()
    targets = _target_files(memory_dir, args.mode)
    plans: list[FilePlan] = []
    for path in targets:
        original = read_text(path)
        updated, matches, blockers = _remove_units(original, topic)
        plans.append(FilePlan(path, updated, matches, blockers))
    matched_plans = [plan for plan in plans if plan.matches]

    tombstone_path = memory_dir / "do-not-use.md"
    tombstone_updated: str | None = None
    tombstone_blockers: tuple[MarkdownUnit, ...] = ()
    if args.mode in {"hard", "purge"}:
        candidate, _matches, tombstone_blockers = _update_existing_tombstones(
            read_text(tombstone_path),
            topic,
            args.mode,
            project_id,
            tombstone_suffix,
        )
        if candidate != ensure_newline(read_text(tombstone_path)):
            tombstone_updated = candidate
    tombstone = _tombstone(topic, args.mode, project_id, tombstone_suffix)
    if args.mode == "soft" and tombstone:
        tombstone_updated = _prepend_entry(read_text(tombstone_path), tombstone)

    changelog_path = memory_dir / "changelog.md"
    changelog_plan = next((plan for plan in plans if plan.path == changelog_path), None)
    changelog_base = (
        changelog_plan.updated
        if changelog_plan
        else (read_text(changelog_path) if changelog_path.exists() else "")
    )
    changelog_message = (
        f"Forgot topic '{topic}' with mode soft."
        if args.mode == "soft"
        else f"Completed {args.mode} forget operation."
    )
    changelog_updated = (
        _append_changelog_entry(changelog_base, changelog_message)
        if changelog_path.exists()
        else None
    )
    writes: list[tuple[Path, str]] = [
        (plan.path, plan.updated)
        for plan in matched_plans
        if plan.path != changelog_path
    ]
    if tombstone_updated is not None:
        writes.append((tombstone_path, tombstone_updated))
    if changelog_updated is not None:
        writes.append((changelog_path, changelog_updated))
    blockers = [
        f"{plan.path.relative_to(memory_dir).as_posix()}: "
        f"{unit.kind} contains non-removable matching content"
        for plan in plans
        for unit in plan.blockers
    ]
    blockers.extend(
        f"do-not-use.md: {unit.kind} contains non-removable matching content"
        for unit in tombstone_blockers
    )
    blockers.extend(_subject_reference_blockers(memory_dir, plans, tombstone_updated))
    active_matches = any(
        plan.matches and not plan.path.relative_to(memory_dir).as_posix().startswith("archive/")
        for plan in plans
    )
    archive_matches = any(
        plan.matches and plan.path.relative_to(memory_dir).as_posix().startswith("archive/")
        for plan in plans
    )
    scope = scope_for_forget(
        args.mode,
        active_matches=active_matches or bool(tombstone_updated),
        archive_matches=archive_matches,
        has_mutations=bool(writes),
    )
    return MutationPlan(
        "forget",
        {"topic": topic, "mode": args.mode, "allow_broad_match": args.allow_broad_match},
        project_id or "legacy-protocol-0.5",
        protocol_version,
        tuple(
            TextMutation(path, ensure_newline(updated))
            for path, updated in writes
        ),
        ("Git history, backups, caches, and external copies are out of scope.",)
        if args.mode == "purge"
        else (),
        tuple(blockers),
        context={"erasure_scope": scope.canonical()},
        project_root=project_root,
        public_arguments={
            "topic": "[redacted]",
            "mode": args.mode,
            "allow_broad_match": args.allow_broad_match,
        }
        if args.mode in {"hard", "purge"}
        else None,
        private_context={"privacy_nonce": privacy_nonce}
        if privacy_nonce is not None
        else None,
        sensitive=args.mode in {"hard", "purge"},
        public_redactions=(topic,) if args.mode in {"hard", "purge"} else (),
    )


def run(args) -> int:
    topic = args.topic.strip()
    if not topic:
        raise ValueError("Forget topic must not be empty.")
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory not found: {memory_dir}")
    if not (memory_dir / "manifest.md").exists():
        raise ValueError("manifest.md is missing; forgetting cannot safely resolve active memory")
    if not (memory_dir / "do-not-use.md").exists():
        raise ValueError("do-not-use.md is missing; forgetting cannot safely record removal guards")
    manifest_text = read_text(memory_dir / "manifest.md")
    metadata = protocol_metadata(manifest_text)
    comparison = compare_versions(
        metadata.get("protocol_version", "0.5"),
        CURRENT_PROTOCOL_VERSION,
    )
    if comparison is None:
        raise ValueError("Project manifest has an invalid protocol version.")
    if comparison > 0:
        raise ValueError("Project protocol is newer than this CLI supports.")
    protocol_06 = comparison == 0
    project_id = project_id_from_manifest(manifest_text) if protocol_06 else None
    tombstone_suffix: str | None = None
    tombstone_seed_path: Path | None = None
    privacy_seed_path: Path | None = None
    privacy_nonce: str | None = None
    if args.mode in {"hard", "purge"}:
        if protocol_06:
            source_digest = digest_text(
                f"{project_id}\0{args.mode}\0{topic}"
            )
            if args.mode == "hard":
                suffixes, tombstone_seed_path = pending_entry_suffixes(
                    "forget-tombstone",
                    project_root,
                    source_digest,
                    ["hard-tombstone"],
                )
                tombstone_suffix = suffixes["hard-tombstone"]
            privacy_nonce, privacy_seed_path = pending_plan_nonce(
                "forget-private",
                project_root,
                source_digest,
            )
        elif args.mode == "hard":
            tombstone_suffix = uuid.uuid4().hex[:8]
            privacy_nonce = uuid.uuid4().hex
        else:
            privacy_nonce = uuid.uuid4().hex

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
            tombstone_original,
            topic,
            args.mode,
            project_id,
            tombstone_suffix,
        )
        if candidate != ensure_newline(tombstone_original):
            tombstone_updated = candidate
    manual_blockers = sum(len(plan.blockers) for plan in plans) + len(tombstone_blockers)
    broad_reasons: list[str] = []
    if len("".join(topic.split())) < 4:
        broad_reasons.append("topic has fewer than four non-whitespace characters")
    if total_matches + len(tombstone_matches) + manual_blockers > 1:
        broad_reasons.append("plan matches more than one semantic unit")

    tombstone = _tombstone(topic, args.mode, project_id, tombstone_suffix)
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
            print(
                f"- {_public_text(relative, topic, redact)}: "
                f"{_summary(unit, redact, number)}"
            )
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
                print(
                    f"- {_public_text(relative, topic, redact)}: "
                    f"{unit.kind} contains matching content"
                )
        for unit in tombstone_blockers:
            print(f"- do-not-use.md: {unit.kind} contains matching content")
    if args.mode == "purge":
        print("Warning: Git history, backups, caches, and external copies are outside this command's scope.")
    writes: list[tuple[Path, str]] = [
        (plan.path, plan.updated) for plan in matched_plans if plan.path != changelog_path
    ]
    if tombstone_updated is not None:
        writes.append((tombstone_path, tombstone_updated))
    if changelog_updated is not None:
        writes.append((changelog_path, changelog_updated))
    mutation_plan = _build_forget_mutation_plan(
        args,
        project_root,
        memory_dir,
        project_id,
        metadata.get("protocol_version", "0.5"),
        tombstone_suffix,
        privacy_nonce,
    )
    scope = ErasureScope(**mutation_plan.context["erasure_scope"])
    public_blockers = mutation_plan.canonical()["blockers"]
    structural_blockers = [
        blocker
        for blocker in public_blockers
        if "cannot remove MC-SUBJ-" in blocker
    ]
    if structural_blockers:
        print(f"Manual rewrite required: {len(structural_blockers)} Subject relationship blocker(s)")
        for blocker in structural_blockers:
            print(f"- {blocker}")
    effective_blockers = bool(mutation_plan.blockers)
    render_scope(scope)
    print_plan(mutation_plan)
    if not args.apply:
        if effective_blockers:
            print("Dry run only. Rewrite the listed content semantically, then preview again before applying.")
        else:
            print("Dry run only. Re-run with --apply" + (" --confirm-plan <PLAN_ID>." if protocol_06 else "."))
        return 0
    if effective_blockers:
        print("Refusing apply: rewrite the listed body/preamble content semantically, then preview again.")
        return 1
    if broad_reasons and not args.allow_broad_match:
        print("Refusing broad-risk apply: " + "; ".join(broad_reasons) + ". Re-run with --allow-broad-match after review.")
        return 1

    if protocol_06 and not args.confirm_plan:
        raise ValueError("Protocol 0.6 forget apply requires --confirm-plan <PLAN_ID>.")
    with project_mutation_guard(
        project_root,
        memory_dir / "manifest.md",
        "forget",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
        allow_legacy=True,
    ) as guard:
        current_metadata = protocol_metadata(guard.manifest_text or "")
        current_comparison = compare_versions(
            current_metadata.get("protocol_version", "0.5"),
            CURRENT_PROTOCOL_VERSION,
        )
        if current_comparison is None:
            raise ValueError(
                "Project protocol became invalid before forget apply."
            )
        current_protocol_06 = current_comparison == 0
        if protocol_06:
            if guard.project_id != project_id:
                raise ValueError(
                    "Project identity changed before forget apply; preview again."
                )
            current_plan = _build_forget_mutation_plan(
                args,
                project_root,
                memory_dir,
                project_id,
                current_metadata.get("protocol_version", "0.5"),
                tombstone_suffix,
                privacy_nonce,
            )
            if current_plan.plan_id != args.confirm_plan:
                print_plan(current_plan)
                raise ValueError(
                    f"Stale or mismatched plan: confirmed {args.confirm_plan}, "
                    f"current Plan ID is {current_plan.plan_id}. No files written."
                )
        elif current_protocol_06:
            raise ValueError(
                "Project migrated to Protocol 0.6 before compatibility forget apply; "
                "preview again and confirm the new Plan ID."
            )
        elif current_comparison > 0:
            raise ValueError(
                "Project protocol became newer than this CLI supports before "
                "compatibility forget apply; update MemoryCustodian."
            )
        else:
            print(
                "Migration available: Protocol 0.5 apply keeps legacy confirmation "
                "behavior under the bootstrap mutation guard."
            )
            current_plan = _build_forget_mutation_plan(
                args,
                project_root,
                memory_dir,
                None,
                current_metadata.get("protocol_version", "0.5"),
                tombstone_suffix,
                privacy_nonce,
            )
        completed_paths = apply_mutations(list(current_plan.mutations))
    completed = [path.relative_to(memory_dir).as_posix() for path in completed_paths]

    print(f"Applied forgetting plan. Written files: {len(completed)}")
    for name in completed:
        print(f"- {_public_text(name, topic, redact)}")
    discard_pending_seed(tombstone_seed_path)
    discard_pending_seed(privacy_seed_path)
    render_apply_boundary()
    return 0
