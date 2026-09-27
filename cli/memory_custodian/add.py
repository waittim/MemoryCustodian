"""Add evidence-backed active memory or an unconfirmed inbox candidate."""

from __future__ import annotations

from pathlib import Path
import hashlib
import re

from .entries import (
    LEGACY_ENTRY_SCHEMA_VERSION,
    generate_entry_id,
    line_safe_markdown_body,
    memory_entry_ids,
    parse_structured_entries,
    render_active_entry,
    render_candidate_entry,
    render_markdown_bullet,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    structured_relation_issues,
    supersede_entry,
    validate_evidence,
    validate_scope,
)
from .local_overlay import LocalStatus, inspect_overlay
from .locking import (
    create_private_file,
    discard_private_file,
    project_mutation_guard,
    read_private_file,
)
from .mutations import TextMutation, apply_mutations
from .plans import MutationPlan, digest_path, pending_plan_directory, print_plan
from .output import publish_data, publish_finding
from .results import make_finding, stable_path
from .transactions import apply_plan_transaction
from .protocol import (
    CURRENT_ENTRY_SCHEMA_VERSION,
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    budget_for,
    budget_state,
    changelog_text,
    compare_versions,
    entry_schema_version_for_manifest,
    estimate_tokens,
    is_indexable_optional_path,
    is_safe_memory_name,
    manifest_with_optional_module_index,
    manifest_contract_metadata,
    managed_markdown_files,
    parse_markdown_units,
    prepended_text,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
from .markdown import visible_lines
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


_LEGACY_TYPED_FIELDS = {
    "decision": "Decision",
    "constraint": "Constraint",
    "preference": "Preference",
    "tombstone": "Rejected",
    "do-not-use": "Rejected",
    "rule": "Rule",
    "profile": "Profile",
    "area": "Decision",
}
_LEGACY_SELECTOR_RE = re.compile(r"^(.+):([0-9]+)$")


class DecisionBudgetError(ValueError):
    pass


def parse_legacy_selector(
    memory_dir: Path,
    selector: str,
    *,
    text: str | None = None,
) -> tuple[Path, int, object, str, str | None]:
    """Resolve ``<managed-file>:<unit-index>`` for explicit migration input.

    Unit indexes intentionally use the same zero-based ordering returned by
    ``parse_markdown_units`` and used by the migration seed logic.  Only H2
    units are admissible: a top-level bullet has no trustworthy title and is
    therefore left for an explicit human rewrite.
    """

    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("--from-legacy requires <file>:<unit-index>.")
    match = _LEGACY_SELECTOR_RE.fullmatch(selector.strip())
    if match is None:
        raise ValueError("--from-legacy requires <file>:<unit-index> with a numeric unit index.")
    relative = Path(match.group(1).replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("--from-legacy file must be a safe memory-relative Markdown path.")
    path = memory_dir.joinpath(*relative.parts)
    try:
        path.relative_to(memory_dir)
    except ValueError as exc:
        raise ValueError("--from-legacy file must remain inside the memory directory.") from exc
    if path.suffix.casefold() != ".md" or not path.exists():
        raise ValueError(f"Legacy source file does not exist: {relative.as_posix()}")
    managed = {item for item in managed_markdown_files(memory_dir)}
    if path not in managed:
        raise ValueError(f"Legacy source is not a managed Markdown file: {relative.as_posix()}")
    source = text if text is not None else read_managed_text(memory_dir, path)
    document = parse_markdown_units(source)
    index = int(match.group(2))
    if index >= len(document.units):
        raise ValueError(
            f"Legacy unit index {index} is out of range for {relative.as_posix()} "
            f"(found {len(document.units)} units)."
        )
    unit = document.units[index]
    if unit.kind != "h2":
        raise ValueError(
            "--from-legacy selects a non-H2 unit; top-level bullets require an explicit semantic rewrite."
        )
    if unit.heading and re.search(r"\bMC-(?:DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-", unit.heading, re.I):
        raise ValueError("--from-legacy may only select a legacy H2 without a canonical Entry ID.")
    typed = None
    lines = unit.text.splitlines()
    boundaries: list[tuple[int, str, str]] = []
    for line in visible_lines(unit.text):
        if line.index == 0 or line.indented_code:
            continue
        field = re.fullmatch(r"([A-Za-z][A-Za-z-]*):[ \t]*(.*)", line.text)
        if field:
            boundaries.append((line.index, field.group(1), field.group(2)))
    typed_names = set(_LEGACY_TYPED_FIELDS.values())
    typed_positions = [item for item in boundaries if item[1] in typed_names]
    if len(typed_positions) != 1:
        raise ValueError(
            "Legacy H2 must contain exactly one unambiguous typed body field "
            "(for example `Decision:` or `Constraint:`)."
        )
    body_index, body_name, inline = typed_positions[0]
    typed = body_name
    next_boundary = next(
        (item[0] for item in boundaries if item[0] > body_index and item[1] in {"Reason", *typed_names}),
        len(lines),
    )
    body_lines = lines[body_index + 1:next_boundary]
    if inline.strip():
        body_lines.insert(0, inline)
    body = "\n".join(body_lines).strip("\n")
    if not body.strip():
        raise ValueError("Selected legacy H2 has an empty typed body.")
    reason = None
    reason_boundary = next(
        (item for item in boundaries if item[0] > body_index and item[1] == "Reason"),
        None,
    )
    if reason_boundary is not None:
        reason_index, _reason_name, reason_inline = reason_boundary
        reason_lines = lines[reason_index + 1:]
        if reason_inline.strip():
            reason_lines.insert(0, reason_inline)
        reason = "\n".join(reason_lines).strip("\n") or None
    return path, index, unit, body, reason


def replace_legacy_unit(
    memory_dir: Path,
    selector: str,
    replacement: str,
    *,
    text: str | None = None,
) -> tuple[Path, int, str]:
    """Replace one selected H2 while preserving all unrelated source ranges."""

    path, index, unit, _body, _reason = parse_legacy_selector(
        memory_dir, selector, text=text,
    )
    source = text if text is not None else read_managed_text(memory_dir, path)
    lines = source.splitlines(keepends=True)
    start, end = unit.start_line, unit.end_line
    old_count = len(unit.text.splitlines())
    if start < 0 or end > len(lines) or start + old_count > end:
        raise ValueError("Legacy source changed while building the canonicalization mutation.")
    original = lines[start:end]
    eol = "\r\n" if any(line.endswith("\r\n") for line in original) else "\n"
    replacement_lines = [line + eol for line in replacement.splitlines()]
    trailing = lines[start + old_count:end]
    lines[start:end] = [*replacement_lines, *trailing]
    return path, index, "".join(lines)


def _title(message: str) -> str:
    clean = " ".join(message.strip().split())
    return clean[:72].rstrip() if clean else "Untitled memory"


def _legacy_entry(kind: str, message: str, reason: str | None) -> str:
    safe_message = line_safe_markdown_body(
        message,
        entry_schema_version=LEGACY_ENTRY_SCHEMA_VERSION,
    )
    safe_reason = (
        line_safe_markdown_body(
            reason,
            entry_schema_version=LEGACY_ENTRY_SCHEMA_VERSION,
        )
        if reason else None
    )
    if kind == "decision":
        body = f"## {today()} - {_title(message)}\nDecision:\n{safe_message}"
        return body + (f"\nReason:\n{safe_reason}" if safe_reason else "")
    if kind in {"constraint", "preference", "rule", "profile", "area"}:
        return render_markdown_bullet(message)
    if kind in {"tombstone", "do-not-use"}:
        return f"## Tombstone: {_title(message)}\n{safe_message}" + (f"\nReason:\n{safe_reason}" if safe_reason else "")
    return f"## {today()}\n- {safe_message}"


def _initial_target_text(
    memory_dir: Path, path: Path, kind: str, name: str | None, area: str | None = None
) -> str:
    if path.exists():
        return read_managed_text(memory_dir, path)
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
    explicit_scope = getattr(args, "scope", None)
    if explicit_scope:
        normalized_scope = validate_scope(explicit_scope)
        if getattr(args, "area", None):
            expected = f"area:{args.area}"
            if normalized_scope.casefold() != expected.casefold():
                raise ValueError("--scope and --area must identify the same scope.")
        if normalized_scope.casefold().startswith("area:") and kind in AREA_SCOPED_TYPES:
            area_name = normalized_scope.split(":", 1)[1]
            return f"areas/{area_name}.md", normalized_scope
        return TARGETS.get(kind, "inbox.md"), normalized_scope
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
        if args.name.casefold() == "readme":
            raise ValueError("README.md is reserved documentation, not a managed module")
        folder = "rules" if kind == "rule" else f"{kind}s"
        return f"{folder}/{args.name}.md", f"area:{args.name}" if kind == "area" else "project"
    return TARGETS[kind], "project"


def _report_budget(
    project_root: Path,
    memory_dir: Path,
    path: Path,
    target: str,
) -> None:
    budget = budget_for(target)
    if budget is None:
        return
    tokens = estimate_tokens(read_managed_text(memory_dir, path))
    state = budget_state(tokens, budget)
    publish_data(budget_result={
        "path": stable_path(
            target, project_root=project_root, memory_dir=memory_dir,
        ),
        "tokens": tokens,
        "limit": budget,
        "state": state,
    })
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
        publish_finding(make_finding(
            "MC-BUDGET-001",
            "WARNING",
            f"{target} is over its context budget.",
            path=target,
            remediation=f"Run `memory-custodian compact --target {target}`.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
        print(f"Warning: {target} is over its context budget.")
        if target == "decisions.md":
            print("Next: consolidate or relocate scoped decisions before considering age-based archival.")
    else:
        publish_finding(make_finding(
            "MC-BUDGET-001",
            "WARNING",
            f"{target} is near its context budget.",
            path=target,
            remediation=f"Run `memory-custodian compact --target {target}`.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))


def _find_entry(
    memory_dir: Path,
    entry_id: str,
    *,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
):
    matches = []
    for path in managed_markdown_files(memory_dir):
        if (
            path.relative_to(memory_dir).as_posix().startswith("archive/")
            or path.name.casefold() == "readme.md"
        ):
            continue
        matches.extend(
            entry for entry in parse_structured_entries(
                path,
                read_managed_text(memory_dir, path),
                entry_schema_version=entry_schema_version,
            )
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
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> tuple[str | None, str | None]:
    subject_id = args.subject.strip() if args.subject else None
    facet = args.facet.strip().casefold() if args.facet else None
    area_context = getattr(args, "area", None)
    if area_context is None and scope.casefold().startswith("area:"):
        area_context = scope.split(":", 1)[1]
    required = subject_required(kind, candidate=candidate, area=area_context)
    if required and (not subject_id or not facet):
        raise ValueError(
            f"Protocol 0.8 active {kind} memory requires both --subject MC-SUBJ-... and --facet."
        )
    if bool(subject_id) != bool(facet):
        raise ValueError("--subject and --facet must be supplied together.")
    old = None
    if getattr(args, "supersedes", None):
        old = _find_entry(
            memory_dir,
            args.supersedes,
            entry_schema_version=entry_schema_version,
        )
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
    normalized_facet = validate_facet("area" if area_context and kind == "decision" else kind, facet)
    if candidate:
        return subject.subject_id, normalized_facet

    owner = None
    for path in managed_markdown_files(memory_dir):
        relative = path.relative_to(memory_dir).as_posix()
        if relative.startswith("archive/") or relative in {"subjects.md", "inbox.md"}:
            continue
        for entry in parse_structured_entries(
            path,
            read_managed_text(memory_dir, path),
            entry_schema_version=entry_schema_version,
        ):
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
    if owner and (
        not getattr(args, "supersedes", None)
        or owner.entry_id.casefold() != args.supersedes.casefold()
    ):
        raise ValueError(
            f"Active structural owner already exists: {owner.entry_id} "
            f"for {scope} + {subject.subject_id} + {normalized_facet}. "
            "Use --supersedes, adjust Scope, or review the Subject."
        )
    if getattr(args, "supersedes", None):
        assert old is not None
        old_subject = old.fields.get("Subject")
        old_facet = old.fields.get("Facet")
        if (old_subject or "").casefold() != subject.subject_id.casefold():
            raise ValueError("--supersedes must retain the old entry's Subject identity.")
        if (old_facet or "").casefold() != normalized_facet:
            raise ValueError("--supersedes must retain the old entry's Facet.")
    return subject.subject_id, normalized_facet


def _build_mutations(
    args,
    project_root: Path,
    memory_dir: Path,
    protocol_06: bool,
    *,
    fixed_id: str | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
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
        metadata = manifest_contract_metadata(
            read_managed_text(memory_dir, memory_dir / "manifest.md")
        )
        overlay = inspect_overlay(
            project_root,
            metadata["project_id"],
            shared_ids=ids,
            entry_schema_version=entry_schema_version,
        )
        if overlay.status == LocalStatus.REVIEW:
            detail = "; ".join(overlay.warnings) or "local overlay requires review"
            raise ValueError(
                "Cannot allocate a shared Entry ID while local overlay integrity is unresolved: "
                + detail
            )
        if overlay.status == LocalStatus.BOUND:
            # ``inspect_overlay`` captured each module with the manifest's
            # Entry grammar.  Reserve IDs from that same parsed view instead
            # of reopening private files with a schema-agnostic heading scan.
            for captured in overlay.captured_modules:
                ids.update(entry.entry_id for entry in captured.entries)
        subject_id, facet = _validate_subject_and_conflict(
            args,
            project_root,
            memory_dir,
            kind=kind,
            scope=scope,
            candidate=candidate,
            entry_schema_version=entry_schema_version,
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
    original = _initial_target_text(memory_dir, target_path, kind, args.name, args.area)
    updated = prepended_text(
        original, entry, remove_lines=("No unprocessed memory candidates.",) if candidate else ()
    )
    mutations = [TextMutation(target_path, updated)]
    if getattr(args, "supersedes", None):
        old = _find_entry(
            memory_dir,
            args.supersedes,
            entry_schema_version=entry_schema_version,
        )
        if old.path == target_path:
            mutations[0] = TextMutation(
                target_path,
                supersede_entry(
                    updated,
                    old.entry_id,
                    new_id,
                    relative_path=target,
                    entry_schema_version=entry_schema_version,
                ),
            )
        else:
            mutations.append(
                TextMutation(old.path, supersede_entry(
                    read_managed_text(memory_dir, old.path),
                    old.entry_id,
                    new_id,
                    relative_path=old.path.relative_to(memory_dir).as_posix(),
                    entry_schema_version=entry_schema_version,
                ))
            )

    manifest_path = memory_dir / "manifest.md"
    if is_indexable_optional_path(target):
        manifest_updated, indexed = manifest_with_optional_module_index(
            read_managed_text(memory_dir, manifest_path), target
        )
        if indexed:
            mutations.append(TextMutation(manifest_path, manifest_updated))
    changelog = memory_dir / "changelog.md"
    if changelog.exists():
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(read_managed_text(memory_dir, changelog), f"Added {kind} memory to {target}."),
            )
        )
    if args.supersedes:
        resulting: list = []
        for mutation in mutations:
            if mutation.path.suffix.casefold() != ".md":
                continue
            resulting.extend(
                entry
                for entry in parse_structured_entries(
                    mutation.path,
                    mutation.text,
                    entry_schema_version=entry_schema_version,
                )
                if entry.entry_id.casefold() in {
                    args.supersedes.casefold(), new_id.casefold()
                }
            )
        relation_issues = structured_relation_issues(resulting)
        if len(resulting) != 2 or relation_issues:
            detail = "; ".join(relation_issues) or "resulting pair did not resolve exactly once"
            raise ValueError(f"Supersession result is invalid: {detail}")
    return mutations, target, new_id


def build_from_legacy_mutations(
    args,
    project_root: Path,
    memory_dir: Path,
    *,
    fixed_id: str | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> tuple[list[TextMutation], str, str, str]:
    """Build an explicit, source-schema-readable legacy H2 replacement.

    This helper deliberately refuses to infer the title, type, scope,
    evidence, Subject, or Facet.  The selected H2 is replaced in place so a
    manual migration cannot accidentally duplicate a still-active legacy
    unit.  The returned selector path is suitable for a migration transaction
    and the fourth value is the rendered canonical Entry for private-state
    bookkeeping.
    """

    selector = getattr(args, "from_legacy", None)
    if not selector:
        raise ValueError("--from-legacy is required for this helper.")
    required = {
        "title": getattr(args, "title", None),
        "scope": getattr(args, "scope", None),
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise ValueError(
            "--from-legacy requires explicit " + ", ".join([*missing, "--type", "--evidence"]) + "."
        )
    if not args.evidence:
        raise ValueError("--from-legacy requires at least one explicit --evidence value.")
    if getattr(args, "supersedes", None):
        raise ValueError("--from-legacy cannot be combined with --supersedes.")
    kind = args.type
    if kind in {"inbox"} or getattr(args, "candidate", False):
        raise ValueError("--from-legacy creates an active canonical Entry; candidates are not supported.")
    scope = validate_scope(str(args.scope).strip())
    path, index, _unit, body, source_reason = parse_legacy_selector(memory_dir, selector)
    expected_field = _LEGACY_TYPED_FIELDS.get(kind)
    actual_field = _legacy_typed_field(path, memory_dir, selector)
    if expected_field != actual_field:
        raise ValueError(
            f"Selected legacy H2 has {actual_field}: body; --type {kind} requires {expected_field}: body."
        )
    target = path.relative_to(memory_dir).as_posix()
    if kind == "area" and not target.startswith("areas/"):
        raise ValueError("--type area must select a legacy H2 inside areas/<name>.md.")
    if kind == "rule" and not target.startswith("rules/"):
        raise ValueError("--type rule must select a legacy H2 inside rules/<name>.md.")
    if kind == "profile" and not target.startswith("profiles/"):
        raise ValueError("--type profile must select a legacy H2 inside profiles/<name>.md.")

    evidence = validate_evidence(
        args.evidence,
        project_root,
        allow_missing=getattr(args, "allow_missing_evidence", False),
    )
    ids = memory_entry_ids(memory_dir)
    subject_id, facet = _validate_subject_and_conflict(
        args,
        project_root,
        memory_dir,
        kind=kind,
        scope=scope,
        candidate=False,
        entry_schema_version=entry_schema_version,
    )
    id_kind = "area" if kind == "area" else kind
    new_id = fixed_id or generate_entry_id(id_kind, ids)
    if new_id.casefold() in {value.casefold() for value in ids}:
        raise ValueError(f"Entry ID collision: {new_id}")
    reason = args.reason if args.reason is not None else source_reason
    rendered = render_active_entry(
        kind,
        new_id,
        str(args.title).strip(),
        body,
        reason,
        scope,
        evidence,
        subject=subject_id,
        facet=facet,
        entry_schema_version=entry_schema_version,
    )
    original = read_managed_text(memory_dir, path)
    replaced_path, replaced_index, updated = replace_legacy_unit(
        memory_dir,
        selector,
        rendered,
        text=original,
    )
    if replaced_path != path or replaced_index != index:
        raise ValueError("Legacy source selector changed while building the mutation.")
    mutations = [TextMutation(path, updated)]
    changelog = memory_dir / "changelog.md"
    if changelog.exists() and path != changelog:
        mutations.append(
            TextMutation(
                changelog,
                changelog_text(
                    read_managed_text(memory_dir, changelog),
                    f"Canonicalized one legacy H2 unit in {target}.",
                ),
            )
        )
    return mutations, target, new_id, rendered


def _legacy_typed_field(path: Path, memory_dir: Path, selector: str) -> str:
    """Return the one typed body label selected by a legacy selector."""

    _path, _index, _unit, _body, _reason = parse_legacy_selector(memory_dir, selector)
    source = read_managed_text(memory_dir, path)
    document = parse_markdown_units(source)
    unit = document.units[_index]
    labels = set(_LEGACY_TYPED_FIELDS.values())
    values = [
        line.text.split(":", 1)[0]
        for line in visible_lines(unit.text)
        if not line.indented_code
        and line.index > 0
        and re.fullmatch(r"([A-Za-z][A-Za-z-]*):[ \t]*(.*)", line.text)
        and line.text.split(":", 1)[0] in labels
    ]
    if len(values) != 1:
        raise ValueError("Legacy H2 must contain exactly one unambiguous typed body field.")
    return values[0]


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
    for path in managed_markdown_files(memory_dir):
        if (
            not path.relative_to(memory_dir).as_posix().startswith("archive/")
            and path.name.casefold() != "readme.md"
        ):
            values.extend([str(path.relative_to(memory_dir)), digest_path(path)])
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:24]


def _seed_path(fingerprint: str) -> Path:
    return pending_plan_directory() / f"supersede-{fingerprint}.id"


def _legacy_seed_path(fingerprint: str) -> Path:
    return pending_plan_directory() / f"legacy-{fingerprint}.id"


def _legacy_fingerprint(args, memory_dir: Path) -> str:
    selector = str(args.from_legacy)
    source_path, _index, _unit, _body, _reason = parse_legacy_selector(memory_dir, selector)
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    values = [
        "add-from-legacy",
        selector,
        source_digest,
        args.type,
        getattr(args, "title", "") or "",
        getattr(args, "scope", "") or "",
        getattr(args, "subject", "") or "",
        getattr(args, "facet", "") or "",
        getattr(args, "reason", "") or "",
        *args.evidence,
    ]
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:32]


def _run_from_legacy(args, project_root: Path, memory_dir: Path, metadata: dict[str, str]) -> int:
    """Preview/apply one explicit legacy H2 conversion under the mutation lock."""

    entry_schema_version = entry_schema_version_for_manifest(
        read_managed_text(memory_dir, memory_dir / "manifest.md")
    )
    fingerprint = _legacy_fingerprint(args, memory_dir)
    seed_path = _legacy_seed_path(fingerprint)
    fixed_id = read_private_file(seed_path).strip() if seed_path.exists() else None
    mutations, target, new_id, _rendered = build_from_legacy_mutations(
        args,
        project_root,
        memory_dir,
        fixed_id=fixed_id,
        entry_schema_version=entry_schema_version,
    )
    if not fixed_id:
        create_private_file(seed_path, new_id + "\n")
    project_id = metadata.get("project_id") or "legacy-protocol"
    plan = MutationPlan(
        "add --from-legacy",
        {
            "from_legacy": args.from_legacy,
            "type": args.type,
            "title": args.title,
            "scope": args.scope,
            "subject": args.subject,
            "facet": args.facet,
        },
        project_id,
        metadata.get("protocol_version", "0.5"),
        tuple(mutations),
        project_root=project_root,
    )
    print_plan(plan)
    if not args.apply:
        print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
    if not args.confirm_plan:
        raise ValueError("--from-legacy apply requires --confirm-plan <PLAN_ID>.")
    applied = False
    try:
        with project_mutation_guard(
            project_root,
            memory_dir / "manifest.md",
            "add --from-legacy",
            timeout=args.lock_timeout,
            break_stale=args.break_stale_lock,
            allow_legacy=True,
            allow_metadata_repair=True,
            project_id_hint=metadata.get("project_id"),
        ) as guard:
            locked_schema = entry_schema_version_for_manifest(guard.manifest_text or "")
            current_mutations, current_target, current_id, _current_rendered = build_from_legacy_mutations(
                args,
                project_root,
                memory_dir,
                fixed_id=fixed_id or new_id,
                entry_schema_version=locked_schema,
            )
            current_plan = MutationPlan(
                "add --from-legacy",
                {
                    "from_legacy": args.from_legacy,
                    "type": args.type,
                    "title": args.title,
                    "scope": args.scope,
                    "subject": args.subject,
                    "facet": args.facet,
                },
                guard.project_id or project_id,
                metadata.get("protocol_version", "0.5"),
                tuple(current_mutations),
                project_root=project_root,
            )
            if current_plan.plan_id != args.confirm_plan:
                raise ValueError(
                    f"Stale or mismatched plan: confirmed {args.confirm_plan}, "
                    f"current Plan ID is {current_plan.plan_id}. No files written."
                )
            apply_plan_transaction(
                current_plan,
                memory_dir,
                force_journal=len(current_mutations) > 1,
            )
            target, new_id = current_target, current_id
        applied = True
    finally:
        if applied:
            discard_private_file(seed_path)
    print(f"Canonicalized legacy H2 as {new_id} in {memory_dir / target}")
    return 0


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory directory not found: {memory_dir}")
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    metadata = manifest_contract_metadata(
        read_managed_text(memory_dir, manifest_path),
        allow_missing_section=True,
    )
    entry_schema_version = entry_schema_version_for_manifest(
        read_managed_text(memory_dir, manifest_path)
    )
    comparison = compare_versions(metadata.get("protocol_version", "0.5"), CURRENT_PROTOCOL_VERSION)
    if comparison is None:
        raise ValueError("Project manifest has an invalid protocol version.")
    protocol_06 = comparison == 0
    if comparison > 0:
        raise ValueError("Project protocol is newer than this CLI supports.")
    if getattr(args, "from_legacy", None):
        if not args.message is None:
            raise ValueError("Positional message cannot be combined with --from-legacy; use --title.")
        return _run_from_legacy(args, project_root, memory_dir, metadata)
    if args.message is None:
        raise ValueError("add requires a positional message unless --from-legacy is used.")
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
                    "Project migrated to Protocol 0.8 before the compatibility write; "
                    "re-run add with Protocol 0.8 Evidence."
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
                    entry_schema_version=entry_schema_version,
                )
            except DecisionBudgetError as exc:
                print(f"Decision entry budget: over/{DECISION_ENTRY_BUDGET} tokens")
                print(f"Not added: {exc}")
                return 1
            compatibility_plan = MutationPlan(
                "add compatibility", {}, guard.project_id or "legacy-protocol",
                current_metadata.get("protocol_version", "0.5"), tuple(mutations),
                project_root=project_root,
            )
            apply_plan_transaction(compatibility_plan, memory_dir)
    else:
        project_id = metadata["project_id"]
        if args.supersedes:
            fingerprint = _supersede_fingerprint(args, project_id, memory_dir)
            seed_path = _seed_path(fingerprint)
            fixed_id = read_private_file(seed_path).strip() if seed_path.exists() else None
            mutations, target, new_id = _build_mutations(
                args,
                project_root,
                memory_dir,
                True,
                fixed_id=fixed_id or None,
                entry_schema_version=entry_schema_version,
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
                raise ValueError("Protocol 0.8 supersede apply requires --confirm-plan <PLAN_ID>.")
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
                    args,
                    project_root,
                    memory_dir,
                    True,
                    fixed_id=new_id,
                    entry_schema_version=entry_schema_version,
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
                apply_plan_transaction(current_plan, memory_dir)
            discard_private_file(seed_path)
            print(f"Added {args.type} memory {new_id} to {memory_dir / target}")
            print("Written files:")
            for mutation in current_mutations:
                print(f"- {mutation.path}")
            _report_budget(project_root, memory_dir, memory_dir / target, target)
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
                mutations, target, new_id = _build_mutations(
                    args,
                    project_root,
                    memory_dir,
                    True,
                    entry_schema_version=entry_schema_version,
                )
            except DecisionBudgetError as exc:
                print(f"Decision entry budget: over/{DECISION_ENTRY_BUDGET} tokens")
                print(f"Not added: {exc}")
                return 1
            current_plan = MutationPlan(
                "add", {"type": args.type}, project_id,
                CURRENT_PROTOCOL_VERSION, tuple(mutations), project_root=project_root,
            )
            apply_plan_transaction(current_plan, memory_dir)
    print(f"Added {'candidate' if args.candidate or args.type == 'inbox' else args.type} memory {new_id} to {memory_dir / target}")
    if args.type == "decision" and args.allow_long and estimate_tokens(
        read_managed_text(memory_dir, memory_dir / target)
    ) > DECISION_ENTRY_BUDGET:
        publish_finding(make_finding(
            "MC-BUDGET-002",
            "WARNING",
            "An explicitly allowed long decision entry was added.",
            path=target,
            remediation="Review and shorten the decision during the next maintenance pass.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
        print("Warning: adding an explicitly allowed long decision entry.")
    _report_budget(project_root, memory_dir, memory_dir / target, target)
    return 0
