"""Unified Protocol 0.8 project and invocation audit facade.

Audit consumes the shared snapshot and structured command results directly.
Human output is only rendered after the result has been assembled; it is never
parsed back into findings.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from . import check as check_cmd
from .context import invalid_context_result, route_context
from .conflicts import ConflictStatus, analyze_snapshot
from .erasure import scope_for_forget
from .forget import _history_check
from .local_overlay import LocalStatus, inspect_overlay
from .output import print_json, public_payload
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    budget_for,
    budget_state,
    compare_versions,
    estimate_tokens,
    resolve_memory_dir,
    resolve_project_root,
)
from .results import CommandResult, Finding, make_finding, unique_findings
from .snapshot import build_snapshot
from .subjects import FACETS
from .transactions import existing_binding_directories, transaction_inventory


AUDIT_SCHEMA_VERSION = 1
DISCLAIMER = (
    "Forgetting governs managed memory; Git history and distributed copies are outside that guarantee."
)


def _check_args(args, *, focused: str | None = None):
    return SimpleNamespace(
        project_root=args.project_root,
        memory_dir=args.memory_dir,
        privacy=bool(getattr(args, "privacy", False)) if focused is None else False,
        security=bool(getattr(args, "security", False)) if focused is None else False,
        routing=focused == "routing",
        reachability=focused == "reachability",
        freshness=focused == "freshness",
        conflicts=focused == "conflicts",
        merge_base=getattr(args, "merge_base", None) if focused == "conflicts" else None,
    )


def _quality_findings(args, focused: str) -> tuple[Finding, ...]:
    return check_cmd.collect(_check_args(args, focused=focused)).ordered_findings


def _subject_findings(snapshot, *, project_root: Path, memory_dir: Path) -> tuple[Finding, ...]:
    return tuple(
        make_finding(
            getattr(issue, "conflict_code", None) or "MC-CONFLICT-010",
            "ERROR",
            str(issue),
            path="docs/memory/subjects.md",
            project_root=project_root,
            memory_dir=memory_dir,
        )
        for issue in snapshot.subject_issues
    )


def _conflict_findings(snapshot, *, project_root: Path, memory_dir: Path) -> tuple[Finding, ...]:
    status_severity = {
        ConflictStatus.CLEAR: "INFO",
        ConflictStatus.REVIEW: "WARNING",
        ConflictStatus.CONFLICT: "ERROR",
        ConflictStatus.INVALID: "ERROR",
    }
    result = analyze_snapshot(snapshot)
    return tuple(
        make_finding(
            item.code,
            status_severity[item.status],
            item.message,
            path="docs/memory/reconciliations.md" if item.origin == "reconciliation" else "docs/memory",
            entry_id=item.entry_ids[0] if item.entry_ids else None,
            details={
                "entry_ids": list(item.entry_ids),
                "subject_id": item.subject_id or None,
                "facet": item.facet or None,
                "scopes": list(item.scopes),
                "origin": item.origin,
                "status": item.status.value,
            },
            project_root=project_root,
            memory_dir=memory_dir,
        )
        for item in result.findings
    )


def _evidence_findings(snapshot, *, project_root: Path, memory_dir: Path) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for entry in snapshot.entries:
        if not entry.evidence:
            findings.append(make_finding(
                "MC-EVIDENCE-001", "ERROR",
                f"{entry.entry_id} has no admissible Evidence.",
                path=entry.path.relative_to(memory_dir).as_posix(),
                entry_id=entry.entry_id,
                remediation="Add user-confirmed or source-backed evidence.",
                project_root=project_root,
                memory_dir=memory_dir,
            ))
    for subject in snapshot.subjects:
        if not subject.evidence:
            findings.append(make_finding(
                "MC-EVIDENCE-001", "ERROR",
                f"{subject.subject_id} has no admissible Evidence.",
                path="docs/memory/subjects.md",
                entry_id=subject.subject_id,
                remediation="Add user-confirmed or source-backed evidence.",
                project_root=project_root,
                memory_dir=memory_dir,
            ))
    return tuple(findings)


def _relation_findings(snapshot, *, project_root: Path, memory_dir: Path) -> tuple[Finding, ...]:
    findings: list[Finding] = [
        make_finding(
            "MC-RELATION-001", "ERROR", str(message),
            path="docs/memory", project_root=project_root, memory_dir=memory_dir,
        )
        for message in (*snapshot.relation_issues, *snapshot.integrity_relation_issues)
    ]
    findings.extend(
        make_finding(
            "MC-CONFLICT-004", "ERROR", issue.message,
            path="docs/memory/reconciliations.md",
            entry_id=issue.entries[0] if issue.entries else None,
            details={"entry_ids": list(issue.entries), "record_id": issue.record_id or None},
            project_root=project_root,
            memory_dir=memory_dir,
        )
        for issue in snapshot.reconciliation_issues
    )
    return tuple(findings)


def _budget_findings(snapshot, *, project_root: Path, memory_dir: Path) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for item in snapshot.files:
        limit = budget_for(item.relative)
        if limit is None:
            continue
        tokens = estimate_tokens(item.text)
        state = budget_state(tokens, limit)
        if state == "OK":
            continue
        severity = "ERROR" if state == "OVER BUDGET" else "WARNING"
        findings.append(make_finding(
            "MC-BUDGET-001", severity,
            f"{item.relative}: {state.lower()} ({tokens}/{limit} tokens).",
            path=item.relative,
            remediation=f"Run `memory-custodian compact --target {item.relative}` after semantic review.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
    return tuple(findings)


def _local_findings(snapshot, project_root: Path, memory_dir: Path) -> tuple[Finding, ...]:
    metadata = snapshot.manifest_contract.as_dict()
    project_id = metadata.get("project_id")
    if not project_id or compare_versions(metadata.get("protocol_version", "0.5"), CURRENT_PROTOCOL_VERSION) != 0:
        return ()
    try:
        overlay = inspect_overlay(
            project_root,
            project_id,
            shared_ids={entry.entry_id for entry in snapshot.relation_entries},
            entry_schema_version=snapshot.entry_schema_version,
        )
    except (OSError, ValueError) as exc:
        return (make_finding(
            "MC-LOCAL-002", "ERROR", str(exc), path="private/local-overlay",
            project_root=project_root, memory_dir=memory_dir,
        ),)
    if overlay.status == LocalStatus.REVIEW:
        return (make_finding(
            "MC-LOCAL-002", "ERROR",
            "; ".join(overlay.warnings) or "Local overlay requires review.",
            path="private/local-overlay", project_root=project_root, memory_dir=memory_dir,
        ),)
    if overlay.status == LocalStatus.UNBOUND:
        return (make_finding(
            "MC-LOCAL-001", "WARNING", "Local overlay is unbound to this project root.",
            path="private/local-overlay", project_root=project_root, memory_dir=memory_dir,
        ),)
    return ()


def _route_invocation(args, snapshot, project_root: Path, memory_dir: Path):
    try:
        routed = route_context(
            project_root,
            memory_dir,
            supplied_task=args.task,
            supplied_paths=args.path,
            rules=args.rule,
            profiles=args.profile,
            areas=args.area,
            snapshot=snapshot,
        )
    except ValueError as exc:
        invalid = invalid_context_result(
            supplied_task=args.task,
            supplied_paths=args.path,
            rules=args.rule,
            profiles=args.profile,
            areas=args.area,
            error=exc,
        )
        return (
            {"completeness": invalid.completeness.value, "error": str(exc), "modules": []},
            (make_finding(
                "MC-ROUTING-003", "ERROR", str(exc), path="docs/memory/manifest.md",
                project_root=project_root, memory_dir=memory_dir,
            ),),
        )
    modules = [
        {
            "module_id": item.module_id,
            "required": item.required,
            "loaded": item.loaded,
            "disposition": item.disposition.value if item.disposition else None,
            "reasons": [reason.value for reason in item.reasons],
            "details": list(item.details),
        }
        for item in sorted(routed.modules, key=lambda item: item.module_id.casefold())
    ]
    canonical = json.dumps(
        {
            "task": routed.canonical_task,
            "paths": [item.value for item in routed.paths],
            "modules": modules,
            "omissions": [item.unit_ref for item in routed.omissions],
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return (
        {
            "supplied_task": routed.supplied_task,
            "canonical_task": routed.canonical_task,
            "completeness": routed.completeness.value,
            "paths": [item.value for item in routed.paths],
            "explicit_scope": {
                "rules": list(routed.explicit_rules),
                "profiles": list(routed.explicit_profiles),
                "areas": list(routed.explicit_areas),
            },
            "modules": modules,
            "budget_omissions": [item.unit_ref for item in routed.omissions],
            "warnings": list(routed.warnings),
            "incomplete_dimensions": list(routed.incomplete_dimensions),
            "context_sha256": hashlib.sha256(canonical).hexdigest(),
        },
        tuple(
            make_finding(
                "MC-ROUTING-003", "ERROR" if routed.completeness.value == "INVALID" else "WARNING",
                warning, path="docs/memory/manifest.md",
                project_root=project_root, memory_dir=memory_dir,
            )
            for warning in routed.warnings
        ),
    )


def _render_text(result: CommandResult) -> None:
    print("MemoryCustodian audit: " + result.status)
    if result.protocol_version is not None:
        print(f"Protocol: {result.protocol_version}")
    for key in (
        "project_id", "routing_configuration", "entries", "candidates", "local_overlay",
        "evidence_coverage", "conflict_status", "budgets", "transactions", "erasure_policy",
    ):
        value = result.data.get(key)
        if isinstance(value, (str, int, bool)):
            print(f"{key.replace('_', ' ').capitalize()}: {value}")
    print("Findings:")
    if not result.ordered_findings:
        print("- none")
    for item in result.ordered_findings:
        details = item.details
        identity = ""
        if details.get("subject_id") or details.get("facet"):
            identity = f" [Subject: {details.get('subject_id') or '-'}; Facet: {details.get('facet') or '-'}]"
        print(f"- {item.code} {item.severity}: {item.message}{identity}")


def collect(args) -> CommandResult:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    snapshot = build_snapshot(memory_dir, project_root)
    metadata = snapshot.manifest_contract.as_dict()
    protocol = metadata.get("protocol_version")
    project_id = metadata.get("project_id")
    findings: list[Finding] = []

    baseline = check_cmd.collect(_check_args(args))
    findings.extend(baseline.findings)
    selectors = {
        name: bool(getattr(args, name, False))
        for name in (
            "routing", "reachability", "freshness", "evidence", "privacy", "security",
            "relations", "subjects", "conflicts", "budgets", "local", "transactions",
            "erasure", "history_exposure",
        )
    }
    run_all = bool(getattr(args, "all", False)) or not any(selectors.values())
    for focused in ("routing", "reachability", "freshness"):
        if run_all or selectors[focused]:
            findings.extend(_quality_findings(args, focused))
    conflict_result = analyze_snapshot(snapshot)
    if run_all or selectors["subjects"]:
        findings.extend(_subject_findings(snapshot, project_root=project_root, memory_dir=memory_dir))
    if run_all or selectors["conflicts"]:
        findings.extend(_conflict_findings(snapshot, project_root=project_root, memory_dir=memory_dir))
    merge_review_data = None
    if getattr(args, "merge_base", None):
        merge_result = check_cmd.collect(_check_args(args, focused="conflicts"))
        findings.extend(
            item for item in merge_result.findings
            if item.details.get("merge_status") is not None
        )
        merge_review_data = merge_result.data.get("merge_review")
    if run_all or selectors["evidence"]:
        findings.extend(_evidence_findings(snapshot, project_root=project_root, memory_dir=memory_dir))
    if run_all or selectors["relations"]:
        findings.extend(_relation_findings(snapshot, project_root=project_root, memory_dir=memory_dir))
    if run_all or selectors["local"]:
        findings.extend(_local_findings(snapshot, project_root, memory_dir))

    bindings = existing_binding_directories(
        project_root,
        memory_dir,
        (project_id,) if project_id else (),
    )
    inventory = tuple(
        item
        for binding in bindings
        for item in transaction_inventory(binding)
    )
    transaction_codes = {
        "unfinished": ("MC-TRANSACTION-001", "Unfinished transaction requires recovery."),
        "committed-cleanup": ("MC-TRANSACTION-001", "Committed transaction cleanup is pending."),
        "malformed": ("MC-TRANSACTION-002", "Malformed transaction journal requires manual recovery."),
        "unsupported": ("MC-TRANSACTION-002", "Unsupported transaction schema requires manual recovery."),
        "orphan": ("MC-TRANSACTION-003", "Orphan transaction state requires manual recovery."),
        "symlink": ("MC-TRANSACTION-004", "Symlinked transaction state is unsafe."),
        "unsafe": ("MC-TRANSACTION-004", "Unsafe transaction state requires manual recovery."),
    }
    if run_all or selectors["transactions"]:
        findings.extend(
            make_finding(
                transaction_codes.get(item.kind, ("MC-TRANSACTION-004", "Unknown transaction state requires manual recovery."))[0],
                "BLOCKER",
                transaction_codes.get(item.kind, ("MC-TRANSACTION-004", "Unknown transaction state requires manual recovery."))[1],
                path="private/transactions", remediation="Run `memory-custodian recover`.",
                details={"transaction_id": item.transaction_id or item.directory.name, "transaction_state": item.kind},
                project_root=project_root, memory_dir=memory_dir,
            )
            for item in inventory
        )

    history_status = "not-requested"
    if selectors["history_exposure"]:
        selector = getattr(args, "topic", None) or getattr(args, "entry_id", None)
        if not selector:
            findings.append(make_finding(
                "MC-ROUTING-003", "ERROR", "--history-exposure requires --topic or --id.",
                path="docs/memory", project_root=project_root, memory_dir=memory_dir,
            ))
        else:
            history_status = _history_check(project_root, memory_dir, selector, True)
            if history_status == "unavailable":
                findings.append(make_finding(
                    "MC-ERASURE-002", "WARNING", "Git history inspection was unavailable.",
                    path="private/history", project_root=project_root, memory_dir=memory_dir,
                ))
            elif history_status == "reachable-copy-detected":
                findings.append(make_finding(
                    "MC-ERASURE-003", "WARNING",
                    "A reachable historical copy was detected in the inspected repository.",
                    path="private/history", project_root=project_root, memory_dir=memory_dir,
                ))
            else:
                findings.append(make_finding(
                    "MC-ERASURE-004", "INFO",
                    "No reachable copy was detected in this bounded inspection; external copies remain unverified.",
                    path="private/history", project_root=project_root, memory_dir=memory_dir,
                ))

    invocation = None
    if getattr(args, "routing_input", False):
        invocation, invocation_findings = _route_invocation(args, snapshot, project_root, memory_dir)
        findings.extend(invocation_findings)

    subjects = [
        {
            "subject_id": item.subject_id,
            "title": item.title,
            "status": item.status,
            "kind": item.kind,
            "canonical_ref": item.canonical_ref,
            "aliases": list(item.aliases),
            "merged_into": item.merged_into,
        }
        for item in sorted(snapshot.subjects, key=lambda item: item.subject_id.casefold())
    ]
    entries_by_status: dict[str, int] = {}
    for entry in snapshot.entries:
        entries_by_status[entry.status] = entries_by_status.get(entry.status, 0) + 1
    erasure_scope = scope_for_forget(
        "soft", active_matches=False, archive_matches=False, has_mutations=False,
        history_check_status=history_status, operation_phase="no-op",
    ).canonical()
    data: dict[str, object] = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "project_id": project_id,
        "routing_configuration": "VALID" if snapshot.manifest_contract.valid else "INVALID",
        "entries": entries_by_status,
        "candidates": entries_by_status.get("candidate", 0),
        "subjects": subjects,
        "facets": sorted(FACETS),
        "relations": {
            "entry_issues": list(snapshot.relation_issues),
            "reconciliation_count": len(snapshot.reconciliations),
        },
        "reconciliation_findings": [item.canonical() for item in findings if item.code == "MC-CONFLICT-004"],
        "conflict_status": conflict_result.status.value,
        "local_overlay": "disabled" if not project_id else "inspected",
        "evidence_coverage": {
            "entries": sum(bool(entry.evidence) for entry in snapshot.entries),
            "subjects": sum(bool(subject.evidence) for subject in snapshot.subjects),
        },
        "budgets": {
            item.relative: {
                "state": budget_state(estimate_tokens(item.text), budget_for(item.relative)),
                "tokens": estimate_tokens(item.text),
                "limit": budget_for(item.relative),
            }
            for item in snapshot.files if budget_for(item.relative) is not None
        },
        "transactions": "recovery-required" if inventory else "clean",
        "erasure_policy": "bounded; Git history and distributed copies unchanged",
        "erasure_scope": erasure_scope,
        "history_exposure": {"status": history_status},
        "finding_counts": {
            severity: sum(item.severity == severity for item in findings)
            for severity in ("INFO", "WARNING", "ERROR", "BLOCKER")
        },
    }
    if invocation is not None:
        data["invocation"] = invocation
    if merge_review_data is not None:
        data["merge_review"] = merge_review_data
    return CommandResult(
        command="audit",
        protocol_version=protocol,
        data=data,
        findings=unique_findings(findings),
        disclaimers=(DISCLAIMER,),
    )


def run(args) -> int:
    result = collect(args)
    if args.format == "json":
        root = resolve_project_root(args.project_root)
        memory = resolve_memory_dir(root, args.memory_dir)
        print_json(public_payload(result, project_root=root, memory_dir=memory))
    else:
        _render_text(result)
    return result.return_code
