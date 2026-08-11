"""Add evidence-backed active memory or an unconfirmed inbox candidate."""

from __future__ import annotations

from pathlib import Path
import hashlib

from .entries import (
    generate_entry_id,
    line_safe_markdown_body,
    memory_entry_ids,
    parse_structured_entries,
    render_active_entry,
    render_candidate_entry,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    supersede_entry,
    validate_evidence,
    validate_scope,
)
from .locking import (
    create_private_file,
    discard_private_file,
    project_mutation_guard,
    read_private_file,
)
from .mutations import TextMutation, apply_mutations
from .plans import MutationPlan, digest_path, pending_plan_directory, print_plan
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    appended_text,
    budget_for,
    budget_state,
    changelog_text,
    compare_versions,
    estimate_tokens,
    is_indexable_optional_path,
    is_safe_memory_name,
    manifest_with_optional_module_index,
    manifest_contract_metadata,
    prepended_text,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
from .templates import render_area_template, render_profile_template, render_rule_template, render_template
from .subjects import (
    SUBJECT_ID_RE,
    load_subjects,
    subject_indexes,
    subject_required,
    validate_facet,
)

TARGETS = {
    "decision": "decisions.md",
    "constraint": "constraints.md",
    "preference": "preferences.md",
    "tombstone": "do-not-use.md",
    "do-not-use": "do-not-use.md",
    "inbox": "inbox.md",
}
AREA_SCOPED_TYPES = {"decision", "constraint", "preference", "tombstone", "do-not-use"}


class DecisionBudgetError(ValueError):
    pass


def _title(message: str) -> str:
    clean = " ".join(message.strip().split())
    return clean[:72].rstrip() if clean else "Untitled memory"


def _legacy_entry(kind: str, message: str, reason: str | None) -> str:
    safe_message = line_safe_markdown_body(message)
    safe_reason = line_safe_markdown_body(reason) if reason else None
    if kind == "decision":
        body = f"## {today()} - {_title(message)}\nDecision:\n{safe_message}"
        return body + (f"\nReason:\n{safe_reason}" if safe_reason else "")
    if kind in {"constraint", "preference", "rule", "profile", "area"}:
        return f"- {safe_message}"
    if kind in {"tombstone", "do-not-use"}:
        return f"## Tombstone: {_title(message)}\n{safe_message}" + (f"\nReason:\n{safe_reason}" if safe_reason else "")
    return f"## {today()}\n- {safe_message}"


def _initial_target_text(path: Path, kind: str, name: str | None, area: str | None = None) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    if area:
        return render_area_template(area, today())
    if kind == "rule" and name:
        return render_rule_template(name, today())
    if kind == "profile" and name:
        return render_profile_template(name, today())
    if kind == "area" and name:
        return render_area_template(name, today())
    return render_template(TARGETS[kind], today())


def _target(args) -> tuple[str, str]:
    kind = args.type
    if args.candidate or kind == "inbox":
        return "inbox.md", "project" if not args.area else f"area:{args.area}"
    if args.area:
        if args.name:
            raise ValueError("--area and --name cannot be used together")
        if kind not in AREA_SCOPED_TYPES:
            raise ValueError(f"--area cannot be used when --type is {kind}")
        if not is_safe_memory_name(args.area):
            raise ValueError(f"Invalid area name: {args.area}")
        return f"areas/{args.area}.md", f"area:{args.area}"
    if kind in {"rule", "profile", "area"}:
        if not args.name:
            raise ValueError(f"--name is required when --type is {kind}")
        if not is_safe_memory_name(args.name):
            raise ValueError(f"Invalid {kind} name: {args.name}")
        folder = "rules" if kind == "rule" else f"{kind}s"
        return f"{folder}/{args.name}.md", f"area:{args.name}" if kind == "area" else "project"
    return TARGETS[kind], "project"


def _report_budget(path: Path, target: str) -> None:
    budget = budget_for(target)
    if budget is None:
        return
    tokens = estimate_tokens(path.read_text(encoding="utf-8"))
    state = budget_state(tokens, budget)
    print(f"Budget: {target} {tokens}/{budget} tokens")
    print(f"State: {state}")
    if state == "OK":
        return
    print(
        "Maintenance required."
        if state == "OVER BUDGET"
        else "Maintenance recommended before the next write."
    )
    print("Generating maintenance preview...")
    print("Maintenance preview (dry run; no files changed):")
    if target == "decisions.md" or target.startswith("areas/"):
        print(f"- Shorten entries over {DECISION_ENTRY_BUDGET} tokens.")
        print("- Merge duplicates and link superseded decisions.")
        print("- Move subsystem-specific knowledge to the matching area.")
        print("- Confirm active invariants remain reachable before archival.")
    else:
        print("- Review duplicates, obsolete detail, and content that belongs in a scoped module.")
    print(f"Run: memory-custodian compact --target {target}")
    if state == "OVER BUDGET":
        print(f"Warning: {target} is over its context budget.")
        if target == "decisions.md":
            print("Next: consolidate or relocate scoped decisions before considering age-based archival.")


def _find_entry(memory_dir: Path, entry_id: str):
    matches = []
    for path in memory_dir.rglob("*.md"):
        if path.relative_to(memory_dir).as_posix().startswith("archive/"):
            continue
        matches.extend(
            entry for entry in parse_structured_entries(path, path.read_text(encoding="utf-8"))
            if entry.entry_id.casefold() == entry_id.casefold()
        )
    if not matches:
        raise ValueError(f"Entry ID not found: {entry_id}")
    if len(matches) > 1:
        raise ValueError(f"Duplicate Entry ID prevents supersede: {entry_id}")
    return matches[0]


def _validate_subject_and_conflict(
    args,
    project_root: Path,
    memory_dir: Path,
    *,
    kind: str,
    scope: str,
    candidate: bool,
) -> tuple[str | None, str | None]:
    subject_id = args.subject.strip() if args.subject else None
    facet = args.facet.strip().casefold() if args.facet else None
    required = subject_required(kind, candidate=candidate, area=args.area)
    if required and (not subject_id or not facet):
        raise ValueError(
            f"Protocol 0.7 active {kind} memory requires both --subject MC-SUBJ-... and --facet."
        )
    if bool(subject_id) != bool(facet):
        raise ValueError("--subject and --facet must be supplied together.")
    old = None
    if args.supersedes:
        old = _find_entry(memory_dir, args.supersedes)
        old_relative = old.path.relative_to(memory_dir).as_posix()
        operand_issues = [
            *structured_entry_schema_issues(old, old_relative),
            *structured_entry_storage_issues(old, old_relative),
        ]
        try:
            validate_evidence(old.evidence, project_root, allow_internal=True)
        except ValueError as exc:
            operand_issues.append(str(exc))
        if operand_issues:
            raise ValueError(
                f"Superseded Entry {old.entry_id} is structurally invalid: "
                + "; ".join(sorted(set(operand_issues)))
            )
        if old.status != "active":
            replacement = old.fields.get("Superseded-By")
            raise ValueError(
                f"Entry {old.entry_id} is already {old.status}"
                + (f" and was replaced by {replacement}" if replacement else "")
            )
        if old.scope.casefold() != scope.casefold():
            raise ValueError("--supersedes must retain the old entry's Scope.")
    if not subject_id:
        if old is not None and (
            old.fields.get("Subject", "") or old.fields.get("Facet", "")
        ):
            raise ValueError(
                "--supersedes must retain the old entry's Subject and Facet identity."
            )
        return None, None
    if not SUBJECT_ID_RE.fullmatch(subject_id):
        raise ValueError(f"Invalid Subject ID: {subject_id}")
    subjects_by_id, _by_alias, _by_ref = subject_indexes(load_subjects(memory_dir))
    subject = subjects_by_id.get(subject_id.casefold())
    if subject is None:
        raise ValueError(f"Subject does not exist or is inactive: {subject_id}")
    normalized_facet = validate_facet("area" if args.area and kind == "decision" else kind, facet)
    if candidate:
        return subject.subject_id, normalized_facet

    owner = None
    for path in sorted(memory_dir.rglob("*.md")):
        relative = path.relative_to(memory_dir).as_posix()
        if relative.startswith("archive/") or relative in {"subjects.md", "inbox.md"}:
            continue
        for entry in parse_structured_entries(path, path.read_text(encoding="utf-8")):
            if (
                entry.status == "active"
                and entry.scope.casefold() == scope.casefold()
                and entry.fields.get("Subject", "").casefold() == subject.subject_id.casefold()
                and entry.fields.get("Facet", "").casefold() == normalized_facet
            ):
                owner = entry
                break
        if owner:
            break
    if owner and (not args.supersedes or owner.entry_id.casefold() != args.supersedes.casefold()):
        raise ValueError(
            f"Active structural owner already exists: {owner.entry_id} "
            f"for {scope} + {subject.subject_id} + {normalized_facet}. "
            "Use --supersedes, adjust Scope, or review the Subject."
        )
    if args.supersedes:
        assert old is not None
        old_subject = old.fields.get("Subject")
        old_facet = old.fields.get("Facet")
        if (old_subject or "").casefold() != subject.subject_id.casefold():
            raise ValueError("--supersedes must retain the old entry's Subject identity.")
        if (old_facet or "").casefold() != normalized_facet:
            raise ValueError("--supersedes must retain the old entry's Facet.")
    return subject.subject_id, normalized_facet


def _build_mutations(
    args, project_root: Path, memory_dir: Path, protocol_06: bool, *, fixed_id: str | None = None
) -> tuple[list[TextMutation], str, str]:
    kind = args.type
    target, scope = _target(args)
    validate_scope(scope)
    candidate = args.candidate or kind == "inbox"
    if args.supersedes and candidate:
        raise ValueError("--supersedes cannot be used with candidate memory.")
    subject_id: str | None = None
    facet: str | None = None
    evidence = ()
    new_id = ""
    if protocol_06:
        evidence = validate_evidence(
            args.evidence,
            project_root,
            candidate=candidate,
            allow_missing=args.allow_missing_evidence,
        )
        ids = memory_entry_ids(memory_dir)
        subject_id, facet = _validate_subject_and_conflict(
            args,
            project_root,
            memory_dir,
            kind=kind,
            scope=scope,
            candidate=candidate,
        )
        id_kind = (
            "inbox"
            if candidate
            else "area"
            if args.area and kind == "decision"
            else kind
        )
        new_id = fixed_id or generate_entry_id(id_kind, ids)
        if new_id.casefold() in {value.casefold() for value in ids}:
            raise ValueError(f"Entry ID collision: {new_id}")
        if candidate:
            entry = render_candidate_entry(
                new_id, _title(args.message), kind if kind != "inbox" else "note",
                args.message, scope, evidence, args.reason,
                subject=subject_id,
                facet=facet,
            )
        else:
            entry = render_active_entry(
                "area" if args.area and kind == "decision" else kind,
                new_id, _title(args.message), args.message, args.reason, scope, evidence,
                subject=subject_id,
                facet=facet,
                supersedes=args.supersedes,
            )
    else:
        entry = _legacy_entry(kind, args.message, args.reason)

    if kind == "decision" and estimate_tokens(entry) > DECISION_ENTRY_BUDGET and not args.allow_long:
        raise DecisionBudgetError(
            "shorten Decision to one or two sentences and Reason to one sentence; "
            "use --allow-long only after semantic review."
        )

    target_path = memory_dir / target
    original = _initial_target_text(target_path, kind, args.name, args.area)
    updated = prepended_text(
        original, entry, remove_lines=("No unprocessed memory candidates.",) if candidate else ()
    )
    mutations = [TextMutation(target_path, updated)]
    if args.supersedes:
        old = _find_entry(memory_dir, args.supersedes)
        if old.path == target_path:
            mutations[0] = TextMutation(target_path, supersede_entry(updated, old.entry_id, new_id))
        else:
            mutations.append(
                TextMutation(old.path, supersede_entry(old.path.read_text(encoding="utf-8"), old.entry_id, new_id))
            )

    manifest_path = memory_dir / "manifest.md"
    if is_indexable_optional_path(target):
        manifest_updated, indexed = manifest_with_optional_module_index(
            manifest_path.read_text(encoding="utf-8"), target
        )
        if indexed:
            mutations.append(TextMutation(manifest_path, manifest_updated))
    changelog = memory_dir / "changelog.md"
    if changelog.exists():
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(changelog.read_text(encoding="utf-8"), f"Added {kind} memory to {target}."),
            )
        )
    return mutations, target, new_id


def _supersede_fingerprint(args, project_id: str, memory_dir: Path) -> str:
    values = [
        project_id,
        args.supersedes or "",
        args.type,
        args.message,
        args.reason or "",
        args.area or "",
        args.subject or "",
        args.facet or "",
        *args.evidence,
    ]
    for path in sorted(memory_dir.rglob("*.md")):
        if not path.relative_to(memory_dir).as_posix().startswith("archive/"):
            values.extend([str(path.relative_to(memory_dir)), digest_path(path)])
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:24]


def _seed_path(fingerprint: str) -> Path:
    return pending_plan_directory() / f"supersede-{fingerprint}.id"


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory not found: {memory_dir}")
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    metadata = manifest_contract_metadata(
        manifest_path.read_text(encoding="utf-8"),
        allow_missing_section=True,
    )
    comparison = compare_versions(metadata.get("protocol_version", "0.5"), CURRENT_PROTOCOL_VERSION)
    if comparison is None:
        raise ValueError("Project manifest has an invalid protocol version.")
    protocol_06 = comparison == 0
    if comparison > 0:
        raise ValueError("Project protocol is newer than this CLI supports.")
    if not protocol_06:
        print("Migration available: legacy compatibility write; migrate to 0.7 for current governance.")
        with project_mutation_guard(
            project_root,
            manifest_path,
            "add compatibility",
            timeout=args.lock_timeout,
            break_stale=args.break_stale_lock,
            allow_legacy=True,
        ) as guard:
            current_metadata = manifest_contract_metadata(
                guard.manifest_text or "",
                allow_missing_section=True,
            )
            current_comparison = compare_versions(
                current_metadata.get("protocol_version", "0.5"),
                CURRENT_PROTOCOL_VERSION,
            )
            if current_comparison is None:
                raise ValueError(
                    "Project protocol became invalid before the compatibility write."
                )
            if current_comparison == 0:
                raise ValueError(
                    "Project migrated to Protocol 0.7 before the compatibility write; "
                    "re-run add with Protocol 0.7 Evidence."
                )
            if current_comparison > 0:
                raise ValueError(
                    "Project protocol became newer than this CLI supports before "
                    "the compatibility write; update MemoryCustodian."
                )
            try:
                mutations, target, new_id = _build_mutations(
                    args,
                    project_root,
                    memory_dir,
                    False,
                )
            except DecisionBudgetError as exc:
                print(f"Decision entry budget: over/{DECISION_ENTRY_BUDGET} tokens")
                print(f"Not added: {exc}")
                return 1
            apply_mutations(mutations)
    else:
        project_id = metadata["project_id"]
        if args.supersedes:
            fingerprint = _supersede_fingerprint(args, project_id, memory_dir)
            seed_path = _seed_path(fingerprint)
            fixed_id = read_private_file(seed_path).strip() if seed_path.exists() else None
            mutations, target, new_id = _build_mutations(
                args, project_root, memory_dir, True, fixed_id=fixed_id or None
            )
            if not fixed_id:
                create_private_file(seed_path, new_id + "\n")
            plan = MutationPlan(
                "add --supersedes",
                {
                    "type": args.type,
                    "supersedes": args.supersedes,
                    "subject": args.subject,
                    "facet": args.facet,
                    "message": args.message,
                },
                project_id,
                CURRENT_PROTOCOL_VERSION,
                tuple(mutations),
                project_root=project_root,
            )
            print_plan(plan)
            if not args.apply:
                print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
                return 0
            if not args.confirm_plan:
                raise ValueError("Protocol 0.7 supersede apply requires --confirm-plan <PLAN_ID>.")
            with project_mutation_guard(
                project_root,
                manifest_path,
                "add --supersedes",
                timeout=args.lock_timeout, break_stale=args.break_stale_lock,
            ) as guard:
                if guard.project_id != project_id:
                    raise ValueError(
                        "Project identity changed before supersede apply; preview again."
                    )
                current_mutations, target, new_id = _build_mutations(
                    args, project_root, memory_dir, True, fixed_id=new_id
                )
                current_plan = MutationPlan(
                    "add --supersedes",
                    {
                        "type": args.type,
                        "supersedes": args.supersedes,
                        "subject": args.subject,
                        "facet": args.facet,
                        "message": args.message,
                    },
                    project_id,
                    CURRENT_PROTOCOL_VERSION,
                    tuple(current_mutations),
                    project_root=project_root,
                )
                if current_plan.plan_id != args.confirm_plan:
                    raise ValueError(
                        f"Stale or mismatched plan: confirmed {args.confirm_plan}, "
                        f"current Plan ID is {current_plan.plan_id}. No files written."
                    )
                apply_mutations(current_mutations)
            discard_private_file(seed_path)
            print(f"Added {args.type} memory {new_id} to {memory_dir / target}")
            print("Written files:")
            for mutation in current_mutations:
                print(f"- {mutation.path}")
            _report_budget(memory_dir / target, target)
            return 0
        with project_mutation_guard(
            project_root,
            manifest_path,
            "add",
            timeout=args.lock_timeout, break_stale=args.break_stale_lock,
        ) as guard:
            if guard.project_id != project_id:
                raise ValueError("Project identity changed before add; re-run the command.")
            # Every source file is re-read and the mutation plan is rebuilt under the lock.
            try:
                mutations, target, new_id = _build_mutations(args, project_root, memory_dir, True)
            except DecisionBudgetError as exc:
                print(f"Decision entry budget: over/{DECISION_ENTRY_BUDGET} tokens")
                print(f"Not added: {exc}")
                return 1
            apply_mutations(mutations)
    print(f"Added {'candidate' if args.candidate or args.type == 'inbox' else args.type} memory {new_id} to {memory_dir / target}")
    if args.type == "decision" and args.allow_long and estimate_tokens(
        (memory_dir / target).read_text(encoding="utf-8")
    ) > DECISION_ENTRY_BUDGET:
        print("Warning: adding an explicitly allowed long decision entry.")
    _report_budget(memory_dir / target, target)
    return 0
