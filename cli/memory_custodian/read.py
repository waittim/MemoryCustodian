"""Render a deterministic and explainable MemoryCustodian context pack."""

from __future__ import annotations

from pathlib import Path
import sys

from .conflicts import ConflictResult, ConflictStatus, analyze_snapshot
from .context import ContextRoutingResult, route_context
from .context_result import build_context_result, render_context_result
from .local_overlay import (
    LocalOverlay,
    LocalStatus,
    inspect_overlay,
    validated_project_identity,
)
from .protocol import (
    ENTRY_SCHEMA_MIGRATION_MESSAGE,
    resolve_memory_dir,
    resolve_project_root,
)
from .output import publish_data, publish_finding
from .results import make_finding
from .routes import ModuleDisposition, RouteReason, RoutedModule, RoutingCompleteness
from .snapshot import build_snapshot


def _optional_requested(kind: str, names: list[str]) -> list[RoutedModule]:
    """Compatibility helper retained for integrations importing the v0.10 API."""

    reason = {
        "profiles": RouteReason.EXPLICIT_PROFILE,
        "areas": RouteReason.EXPLICIT_AREA,
        "rules": RouteReason.EXPLICIT_RULE,
    }[kind]
    return [RoutedModule(f"{kind}/{name}.md", False, (reason,)) for name in names]


def _reason(module: RoutedModule) -> str:
    primary = next(
        (item for item in (RouteReason.INVALID, RouteReason.MISSING_REQUIRED, RouteReason.OPTIONAL_ABSENT) if item in module.reasons),
        next((item for item in module.reasons if item != RouteReason.BUDGET_OMISSION), module.reasons[0]),
    )
    detail = f" ({'; '.join(module.details)})" if module.details else ""
    return primary.value + detail


def _publish_contract(
    result: ContextRoutingResult,
    *,
    project_root: Path,
    memory_dir: Path,
    snapshot,
    overlay: LocalOverlay,
    completeness: RoutingCompleteness,
    conflicts: ConflictResult,
    local_contents: list[tuple[str, str]],
    local_scope_warnings: list[str],
    migration_required: bool,
    return_code: int,
) -> None:
    """Publish routing facts from the typed routing/snapshot models."""

    groups = {
        "loaded_modules": ModuleDisposition.LOADED,
        "skipped_modules": ModuleDisposition.SKIPPED,
        "missing_required_modules": ModuleDisposition.MISSING_REQUIRED,
        "missing_optional_modules": ModuleDisposition.MISSING_OPTIONAL,
        "invalid_modules": ModuleDisposition.INVALID,
    }
    loaded_modules = {
        item.module_id for item in result.modules if item.disposition == ModuleDisposition.LOADED
    }
    omitted_ids = {
        item.unit_ref.casefold()
        for item in result.omissions
        if item.unit_ref.upper().startswith("MC-")
    }
    loaded_entries = [
        entry
        for entry in snapshot.entries
        if entry.path.relative_to(memory_dir).as_posix() in loaded_modules
        and entry.entry_id.casefold() not in omitted_ids
    ]
    entry_dispositions = [
        {
            "entry_id": entry.entry_id,
            "module": entry.path.relative_to(memory_dir).as_posix(),
            "disposition": "loaded",
            "subject_id": entry.fields.get("Subject") or entry.fields.get("Provisional-Subject"),
            "facet": entry.fields.get("Facet") or entry.fields.get("Provisional-Facet"),
        }
        for entry in loaded_entries
    ]
    for captured in overlay.captured_modules:
        if (f"local/{captured.relative}", captured.text.strip()) not in local_contents:
            continue
        entry_dispositions.extend({
            "entry_id": entry.entry_id,
            "module": f"local/{captured.relative}",
            "disposition": "loaded",
            "subject_id": entry.fields.get("Subject") or entry.fields.get("Provisional-Subject"),
            "facet": entry.fields.get("Facet") or entry.fields.get("Provisional-Facet"),
        } for entry in captured.entries)

    conflict_findings = [
        {
            "code": item.code,
            "status": item.status.value,
            "message": item.message,
            "entry_ids": list(item.entry_ids),
            "subject_id": item.subject_id or None,
            "facet": item.facet or None,
            "scopes": list(item.scopes),
        }
        for item in conflicts.findings
    ]
    explicit_modules = [
        *(f"rule:{item}" for item in result.explicit_rules),
        *(f"profile:{item}" for item in result.explicit_profiles),
        *(f"area:{item}" for item in result.explicit_areas),
    ]
    warnings = [*result.warnings, *local_scope_warnings]
    if migration_required:
        warnings.append(ENTRY_SCHEMA_MIGRATION_MESSAGE)
    publish_data(
        supplied_task=result.supplied_task,
        canonical_task=result.canonical_task,
        normalized_paths=[item.value for item in result.paths],
        explicit_modules=explicit_modules,
        routing_completeness=completeness.value,
        shared_routing_completeness=result.completeness.value,
        local_overlay_status=overlay.status.value,
        module_dispositions=[{
            "module": item.module_id,
            "disposition": item.disposition.value,
            "required": item.required,
            "reason": _reason(item),
            "reasons": [reason.value for reason in item.reasons],
            "details": list(item.details),
        } for item in result.modules],
        entry_dispositions=entry_dispositions,
        loaded_entry_ids=sorted(
            (item["entry_id"] for item in entry_dispositions), key=str.casefold,
        ),
        omitted_entry_ids=sorted(
            (item.unit_ref for item in result.omissions), key=str.casefold,
        ),
        subject_ids=sorted({
            str(item["subject_id"])
            for item in entry_dispositions if item["subject_id"]
        }, key=str.casefold),
        facets=sorted({
            str(item["facet"])
            for item in entry_dispositions if item["facet"]
        }, key=str.casefold),
        budget_omissions=[{
            "unit_ref": item.unit_ref,
            "module": item.module_id,
            "disposition": item.disposition,
            "reason": item.reason.value,
        } for item in result.omissions],
        warnings=warnings,
        conflict_status=conflicts.status.value,
        conflict_findings=conflict_findings,
        reconciliation_findings=[
            item for item in conflict_findings if item["code"] == "MC-CONFLICT-008"
        ],
        incomplete_dimensions=list(dict.fromkeys((
            *result.incomplete_dimensions,
            *(("local-overlay-review",) if overlay.status == LocalStatus.REVIEW else ()),
            *(("invalid-local-scope",) if local_scope_warnings else ()),
        ))),
        **{
            key: [
                item.module_id for item in result.modules if item.disposition == disposition
            ]
            for key, disposition in groups.items()
        },
    )
    for warning in warnings:
        publish_finding(make_finding(
            "MC-ROUTING-003",
            "WARNING",
            warning,
            path="docs/memory/manifest.md",
            remediation="Review the route and manifest before using the context.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
    overlay_warnings = list(overlay.warnings)
    if overlay.status in {LocalStatus.UNBOUND, LocalStatus.REVIEW} and not overlay_warnings:
        overlay_warnings.append(f"Local overlay status is {overlay.status.value}.")
    for warning in overlay_warnings:
        publish_finding(make_finding(
            "MC-LOCAL-001",
            "WARNING",
            warning,
            path="local/",
            remediation="Review and explicitly link or repair the local overlay.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
    for item in conflicts.findings:
        severity = "WARNING" if item.status == ConflictStatus.REVIEW else "BLOCKER"
        publish_finding(make_finding(
            item.code,
            severity,
            item.message,
            path="docs/memory",
            entry_id=item.entry_ids[0] if item.entry_ids else None,
            remediation="Resolve or explicitly reconcile the reported conflict.",
            details={
                "entry_ids": list(item.entry_ids),
                "subject_id": item.subject_id or None,
                "facet": item.facet or None,
                "scopes": list(item.scopes),
            },
            project_root=project_root,
            memory_dir=memory_dir,
        ))
    if return_code == 1:
        publish_finding(make_finding(
            "MC-ROUTING-004",
            "ERROR",
            "The requested context route is not approved.",
            path="docs/memory/manifest.md",
            remediation="Supply the missing routing scope or repair the route and retry.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
    elif return_code == 2 and not any(
        item.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}
        for item in conflicts.findings
    ):
        publish_finding(make_finding(
            "MC-ROUTING-005",
            "BLOCKER",
            "The requested context route is blocked.",
            path="docs/memory/manifest.md",
            remediation="Repair the manifest, migration, or conflict blocker and retry.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    snapshot = build_snapshot(memory_dir, project_root)
    context = build_context_result(
        project_root,
        memory_dir,
        supplied_task=args.task,
        supplied_paths=getattr(args, "path", []),
        rules=getattr(args, "rule", []),
        profiles=args.profile,
        areas=args.area,
        strict_routing=args.strict_routing,
        no_local=getattr(args, "no_local", False),
        snapshot=snapshot,
        # Preserve the compatibility seam used by integrations that patch
        # the read command's routing/local helpers.
        router=route_context,
        overlay_inspector=inspect_overlay,
        identity_validator=validated_project_identity,
        conflict_analyzer=analyze_snapshot,
    )
    sys.stdout.write(render_context_result(
        context,
        explain=args.explain,
        names_only=args.names_only,
    ))
    if context.routing_invalid:
        print(f"Error: {context.routing.warnings[0]}", file=sys.stderr)
    if context.strict_routing and context.rejected:
        print(
            "Strict routing rejected context: "
            f"completeness={context.completeness.value}, "
            f"conflict={context.conflicts.status.value}",
            file=sys.stderr,
        )
    _publish_contract(
        context.routing,
        project_root=project_root,
        memory_dir=memory_dir,
        snapshot=snapshot,
        overlay=context.overlay,
        completeness=context.completeness,
        conflicts=context.conflicts,
        local_contents=list(context.local_contents),
        local_scope_warnings=list(context.local_scope_warnings),
        migration_required=context.migration_required,
        return_code=context.return_code,
    )
    return context.return_code
