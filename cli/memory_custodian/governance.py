"""Transactional relation and reconciliation governance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .conflicts import canonical_entries
from .entries import ENTRY_ID_RE, StructuredEntry, validate_evidence
from .locking import project_mutation_guard
from .mutations import TextMutation
from .plans import MutationPlan, digest_text
from .transactions import apply_plan_transaction
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    manifest_contract_metadata,
    project_id_from_manifest,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
    today,
)
from .reconciliations import (
    RESOLUTIONS,
    ReconciliationRecord,
    parse_reconciliations,
    validate_reconciliations,
)
from .structural import active_structural_operand_issues, subject_index
from .subjects import Subject, load_subjects, validate_subject_registry


@dataclass(frozen=True)
class GovernanceProject:
    project_root: Path
    memory_dir: Path
    project_id: str
    manifest_sha256: str


def _project(args) -> GovernanceProject:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = read_managed_text(memory_dir, memory_dir / "manifest.md")
    metadata = manifest_contract_metadata(manifest)
    version = metadata["protocol_version"]
    comparison = compare_versions(version, CURRENT_PROTOCOL_VERSION)
    if comparison is None:
        raise ValueError(f"Invalid protocol version {version!r} in manifest.md.")
    if comparison < 0:
        raise ValueError(
            f"Governance preview requires Protocol {CURRENT_PROTOCOL_VERSION}; "
            f"project uses {version}. Run `memory-custodian migrate`."
        )
    if comparison > 0:
        raise ValueError(
            f"Project protocol {version} is newer than this CLI supports "
            f"({CURRENT_PROTOCOL_VERSION}); update MemoryCustodian."
        )
    if not (memory_dir / "subjects.md").is_file():
        raise ValueError(
            "Governance preview requires the declared subjects.md registry; "
            "run `memory-custodian init --repair`."
        )
    registry_issues = validate_subject_registry(memory_dir, project_root)
    if registry_issues:
        raise ValueError("Subject registry is invalid: " + "; ".join(registry_issues[:5]))
    project_id = project_id_from_manifest(manifest)
    if not project_id:
        raise ValueError(
            "Governance preview requires manifest project_id metadata; "
            "run `memory-custodian migrate`."
        )
    return GovernanceProject(
        project_root,
        memory_dir,
        project_id,
        digest_text(manifest),
    )


def _entry(entries: tuple[StructuredEntry, ...], entry_id: str) -> StructuredEntry:
    matches = [item for item in entries if item.entry_id.casefold() == entry_id.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Entry ID must resolve exactly once: {entry_id}")
    return matches[0]


def _plan_id(command: str, project_id: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"command": command, "project_id": project_id, **payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _entry_state(entry: StructuredEntry, memory_dir: Path) -> dict[str, str]:
    return {
        "entry_id": entry.entry_id,
        "path": entry.path.relative_to(memory_dir).as_posix(),
        "text_sha256": digest_text(entry.text),
    }


def _replace_entry_source(document: str, entry: StructuredEntry, updated_unit: str) -> str:
    if document.count(entry.text) != 1:
        raise ValueError(f"Entry source must resolve exactly once: {entry.entry_id}")
    return document.replace(entry.text, updated_unit, 1)


def _with_exception(entry: StructuredEntry, target: str | None) -> str:
    import re
    unit = re.sub(r"(?m)^Exception-To:[^\n]*(?:\n|$)", "", entry.text)
    if target is None:
        return unit.rstrip()
    body = next(
        (name for name in ("Decision", "Constraint", "Preference", "Rejected") if entry.field_counts.get(name)),
        None,
    )
    if body is None:
        raise ValueError("Exception source has no canonical typed body.")
    marker = f"\n\n{body}:"
    if marker not in unit:
        raise ValueError("Exception source body boundary is ambiguous.")
    return unit.replace(marker, f"\nException-To: {target}{marker}", 1)


def _exception_relation_blockers(
    area: StructuredEntry,
    baseline: StructuredEntry,
    subjects: dict[str, tuple[Subject, ...]],
) -> list[str]:
    blockers = [
        f"{label} {issue.field}: {issue.message}"
        for label, entry in (("Source", area), ("Target", baseline))
        for issue in active_structural_operand_issues(entry, subjects)
    ]
    if not area.scope.startswith("area:"):
        blockers.append("Exception source must be area-scoped.")
    if baseline.scope != "project":
        blockers.append("Exception target must be project-scoped.")
    for field in ("Subject", "Facet"):
        if area.fields.get(field, "").casefold() != baseline.fields.get(field, "").casefold():
            blockers.append(f"Source and target must have the same {field}.")
    if baseline.fields.get("Exception-To"):
        blockers.append("Exception target must not itself declare Exception-To.")
    return blockers


def _exception_add(args) -> int:
    project = _project(args)
    memory_dir = project.memory_dir
    entries = canonical_entries(memory_dir)
    subjects_path = memory_dir / "subjects.md"
    subjects = subject_index(load_subjects(memory_dir))
    area = _entry(entries, args.entry_id)
    baseline = _entry(entries, args.target_entry_id)
    blockers = _exception_relation_blockers(area, baseline, subjects)
    current = area.fields.get("Exception-To", "")
    if current and current.casefold() != baseline.entry_id.casefold():
        blockers.append(f"Source already has Exception-To: {current}.")
    blockers = list(dict.fromkeys(blockers))

    payload = {
        "source": area.entry_id,
        "target": baseline.entry_id,
        "dependencies": [
            _entry_state(area, memory_dir), _entry_state(baseline, memory_dir),
        ],
        "manifest_sha256": project.manifest_sha256,
        "subjects_sha256": digest_text(read_managed_text(memory_dir, subjects_path)),
        "blockers": sorted(blockers),
    }
    print("Exception-To add preview:")
    print(
        f"Source: {area.entry_id} "
        f"({area.path.relative_to(memory_dir).as_posix()}; {area.scope}; {area.status})"
    )
    print(
        f"Target: {baseline.entry_id} "
        f"({baseline.path.relative_to(memory_dir).as_posix()}; {baseline.scope}; {baseline.status})"
    )
    print(
        f"Structural identity: "
        f"{area.fields.get('Subject', '-')}+{area.fields.get('Facet', '-')}"
    )
    print(f"Proposed relation: Exception-To: {baseline.entry_id}")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    original = read_managed_text(memory_dir, area.path)
    updated = _replace_entry_source(original, area, _with_exception(area, baseline.entry_id))
    plan = MutationPlan(
        "exception add", {"entry_id": area.entry_id, "target_entry_id": baseline.entry_id},
        project.project_id, CURRENT_PROTOCOL_VERSION,
        () if blockers or updated == original else (TextMutation(area.path, updated),),
        blockers=tuple(blockers),
        private_context={
            "dependency_sha256": _plan_id("exception-add", project.project_id, payload),
        },
        project_root=project.project_root,
    )
    print(f"Plan ID: {plan.plan_id}")
    if not args.apply:
        print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
    if blockers:
        return 1
    if args.confirm_plan != plan.plan_id:
        raise ValueError("Stale or mismatched Exception-To plan. No files written.")
    with project_mutation_guard(project.project_root, memory_dir / "manifest.md", "exception add", timeout=args.lock_timeout, break_stale=args.break_stale_lock):
        if plan.plan_id != args.confirm_plan:
            raise ValueError("Exception-To source changed before apply; preview again. No files written.")
        apply_plan_transaction(plan, memory_dir, force_journal=True)
    print("Applied Exception-To relation.")
    return 0


def _exception_remove(args) -> int:
    project = _project(args)
    memory_dir = project.memory_dir
    entries = canonical_entries(memory_dir)
    subjects_path = memory_dir / "subjects.md"
    subjects = subject_index(load_subjects(memory_dir))
    area = _entry(entries, args.entry_id)
    current = area.fields.get("Exception-To", "")
    targets = [item for item in entries if item.entry_id.casefold() == current.casefold()]
    if len(targets) == 1:
        blockers = _exception_relation_blockers(area, targets[0], subjects)
    else:
        blockers = [
            f"Source {issue.field}: {issue.message}"
            for issue in active_structural_operand_issues(area, subjects)
        ]
        if not area.scope.startswith("area:"):
            blockers.append("Exception source must be area-scoped.")
        blockers.append(
            "Source does not have an Exception-To relation."
            if not current else "Exception-To target must resolve exactly once."
        )
    blockers = list(dict.fromkeys(blockers))
    target_label = current or "none"
    resulting_review = len(targets) == 1 and not blockers
    payload = {
        "source": area.entry_id,
        "current_target": current,
        "dependencies": [
            _entry_state(entry, memory_dir) for entry in (area, *targets)
        ],
        "manifest_sha256": project.manifest_sha256,
        "subjects_sha256": digest_text(read_managed_text(memory_dir, subjects_path)),
        "blockers": sorted(blockers),
        "resulting_review": resulting_review,
    }
    print("Exception-To remove preview:")
    print(
        f"Source: {area.entry_id} "
        f"({area.path.relative_to(memory_dir).as_posix()}; {area.scope}; {area.status})"
    )
    print(f"Current relation target: {target_label}")
    print(f"Proposed relation: remove Exception-To: {target_label}")
    print("Resulting review:")
    print(
        "- MC-CONFLICT-002 project/area overlap will require review."
        if resulting_review else "- result not established due to blockers."
    )
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    original = read_managed_text(memory_dir, area.path)
    updated = _replace_entry_source(original, area, _with_exception(area, None))
    plan = MutationPlan(
        "exception remove", {"entry_id": area.entry_id}, project.project_id,
        CURRENT_PROTOCOL_VERSION,
        () if blockers or updated == original else (TextMutation(area.path, updated),),
        blockers=tuple(blockers),
        private_context={
            "dependency_sha256": _plan_id("exception-remove", project.project_id, payload),
        },
        project_root=project.project_root,
    )
    print(f"Plan ID: {plan.plan_id}")
    if not args.apply:
        print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
    if blockers:
        return 1
    if args.confirm_plan != plan.plan_id:
        raise ValueError("Stale or mismatched Exception-To removal plan. No files written.")
    with project_mutation_guard(project.project_root, memory_dir / "manifest.md", "exception remove", timeout=args.lock_timeout, break_stale=args.break_stale_lock):
        if plan.plan_id != args.confirm_plan:
            raise ValueError("Exception-To source changed before apply; preview again. No files written.")
        apply_plan_transaction(plan, memory_dir, force_journal=True)
    print("Removed Exception-To relation; structural overlap remains REVIEW until reconciled.")
    return 0


def _reconcile_preview(args) -> int:
    from .markdown import render_canonical_h2

    project = _project(args)
    project_root = project.project_root
    memory_dir = project.memory_dir
    normalized_entries: dict[str, str] = {}
    for value in args.entry:
        candidate = value.strip().upper()
        if ENTRY_ID_RE.fullmatch(candidate) is None:
            raise ValueError(f"Invalid reconciliation Entry ID: {value}")
        normalized_entries.setdefault(candidate.casefold(), candidate)
    requested = tuple(sorted(normalized_entries.values(), key=str.casefold))
    if len(requested) < 2:
        raise ValueError("Reconciliation preview requires at least two distinct --entry values.")
    evidence = tuple(sorted(dict.fromkeys(
        validate_evidence(args.evidence, project_root)
    ), key=str.casefold))
    title = " ".join(args.title.split())
    if not title:
        raise ValueError("Reconciliation title must not be empty.")
    record_seed = "\0".join([
        project.project_id, args.resolution, title, *requested, *evidence,
    ])
    suffix = hashlib.sha256(record_seed.encode()).hexdigest()[:8]
    record_id = f"MC-REC-{today().replace('-', '')}-{suffix}"
    unit = (
        render_canonical_h2(record_id, title) + "\n\n"
        "Status: active\nEntries:\n"
        + "\n".join(f"- {value}" for value in requested)
        + f"\nResolution: {args.resolution}\nEvidence:\n"
        + "\n".join(f"- {value}" for value in evidence)
    )
    proposed = ReconciliationRecord(
        record_id, title, "active", args.resolution, requested, evidence, unit,
    )
    path = memory_dir / "reconciliations.md"
    existing, parse_issues = (
        parse_reconciliations(
            path,
            read_managed_text(memory_dir, path),
            project_root,
            include_invalid=True,
        ) if path.exists() else ((), ())
    )
    # A reconciliation may explicitly cover a live Entry and its historical
    # replacement under archive/.  The archive participates in relation
    # validation and preview inventory, but remains excluded from ordinary
    # context/owner consumers.
    entries = canonical_entries(memory_dir, include_archive=True)
    _valid, issues = validate_reconciliations(
        (*existing, proposed), parse_issues, entries, load_subjects(memory_dir),
    )
    blockers = [
        (f"{issue.record_id}: " if issue.record_id else "") + issue.message
        for issue in issues
    ]
    payload = {
        "record": unit,
        "base_sha256": digest_text(read_managed_text(memory_dir, path, required=False)),
        "entry_dependencies": [
            _entry_state(entry, memory_dir)
            for entry in sorted(
                entries,
                key=lambda item: (
                    item.entry_id.casefold(), item.path.as_posix(), digest_text(item.text),
                ),
            )
        ],
        "manifest_sha256": project.manifest_sha256,
        "subjects_sha256": digest_text(read_managed_text(memory_dir, memory_dir / "subjects.md")),
        "blockers": blockers,
    }
    print("Reconciliation record preview:")
    print(unit)
    print("Inventory:")
    for value in requested:
        matches = [entry for entry in entries if entry.entry_id.casefold() == value.casefold()]
        if len(matches) == 1:
            entry = matches[0]
            print(
                f"- {entry.entry_id} "
                f"({entry.path.relative_to(memory_dir).as_posix()}; {entry.scope}; {entry.status})"
            )
        else:
            print(f"- {value} (resolves {len(matches)} times)")
    print("Blockers:")
    for blocker in blockers or ["none"]:
        print(f"- {blocker}")
    existing_text = read_managed_text(memory_dir, path, required=False)
    if existing_text:
        updated = existing_text.rstrip() + "\n\n" + unit + "\n"
    else:
        updated = "# Reconciliations\n\nRecords are append-only governance evidence.\n\n" + unit + "\n"
    plan = MutationPlan(
        "reconcile", {"resolution": args.resolution, "entries": requested},
        project.project_id, CURRENT_PROTOCOL_VERSION,
        () if blockers else (TextMutation(path, updated),), blockers=tuple(blockers),
        private_context={
            "dependency_sha256": _plan_id("reconcile", project.project_id, payload),
        },
        project_root=project.project_root,
    )
    print(f"Plan ID: {plan.plan_id}")
    if not args.apply:
        print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
    if blockers:
        return 1
    if args.confirm_plan != plan.plan_id:
        raise ValueError("Stale or mismatched reconciliation plan. No files written.")
    with project_mutation_guard(project.project_root, memory_dir / "manifest.md", "reconcile", timeout=args.lock_timeout, break_stale=args.break_stale_lock):
        if plan.plan_id != args.confirm_plan:
            raise ValueError("Reconciliation inputs changed before apply; preview again. No files written.")
        apply_plan_transaction(plan, memory_dir, force_journal=True)
    print(f"Applied reconciliation record {record_id}.")
    return 0


def run(args) -> int:
    if args.command == "exception":
        return {"add": _exception_add, "remove": _exception_remove}[args.exception_command](args)
    return _reconcile_preview(args)


__all__ = ["RESOLUTIONS", "run"]
