"""Render a deterministic and explainable MemoryCustodian context pack."""

from __future__ import annotations

from pathlib import Path
import sys

from .conflicts import ConflictResult, ConflictStatus, analyze_snapshot, render_conflict_result
from .context import ContextRoutingResult, invalid_context_result, route_context
from .local_overlay import (
    LocalOverlay,
    LocalStatus,
    inspect_overlay,
    render_overlay_status,
    validated_project_identity,
)
from .protocol import (
    ENTRY_SCHEMA_MIGRATION_MESSAGE,
    budget_for,
    resolve_memory_dir,
    resolve_project_root,
)
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


def _render_modules(result: ContextRoutingResult, *, explain: bool) -> None:
    groups = (
        ("Loaded", ModuleDisposition.LOADED),
        ("Skipped optional", ModuleDisposition.SKIPPED),
        ("Missing required", ModuleDisposition.MISSING_REQUIRED),
        ("Missing optional", ModuleDisposition.MISSING_OPTIONAL),
        ("Invalid", ModuleDisposition.INVALID),
    )
    for heading, disposition in groups:
        matches = [item for item in result.modules if item.disposition == disposition]
        print(f"{heading}:")
        if not matches:
            print("- none")
        for module in matches:
            print(f"- {module.module_id}")
            if explain:
                print(f"  Disposition: {module.disposition.value}")
                print(f"  Reason: {_reason(module)}")
                if RouteReason.CANONICAL_TASK in module.reasons:
                    print(f"  Matching input: task:{result.canonical_task}")
                elif RouteReason.EXPLICIT_RULE in module.reasons:
                    print(f"  Matching input: rule:{module.module_id.removeprefix('rules/').removesuffix('.md')}")
                elif RouteReason.EXPLICIT_PROFILE in module.reasons:
                    print(f"  Matching input: profile:{module.module_id.removeprefix('profiles/').removesuffix('.md')}")
                elif RouteReason.EXPLICIT_AREA in module.reasons:
                    print(f"  Matching input: area:{module.module_id.removeprefix('areas/').removesuffix('.md')}")


def _render_header(result: ContextRoutingResult, completeness: RoutingCompleteness) -> None:
    print("# Memory Context Pack")
    print(f"Task: {result.supplied_task}")
    print(f"Canonical task: {result.canonical_task}")
    print("Paths:")
    if result.paths:
        for path in result.paths:
            suffix = " (missing-on-disk)" if path.missing_on_disk else ""
            print(f"- {path.value}{suffix}")
    else:
        print("- none supplied")
    print("Explicit scope:")
    values = [
        *(f"rule:{item}" for item in result.explicit_rules),
        *(f"profile:{item}" for item in result.explicit_profiles),
        *(f"area:{item}" for item in result.explicit_areas),
    ]
    for value in values or ["none supplied"]:
        print(f"- {value}")
    print(f"Routing completeness: {completeness.value}")


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    # Capture all shared managed-memory inputs before routing.  The routing
    # result, budget pack, local shared-ID lookup, and conflict analysis must
    # describe this one immutable view rather than a sequence of disk reads.
    snapshot = build_snapshot(memory_dir, project_root)
    migration_required = snapshot.manifest_contract.migration_available
    routing_invalid = False
    try:
        result = route_context(
            project_root,
            memory_dir,
            supplied_task=args.task,
            supplied_paths=getattr(args, "path", []),
            rules=getattr(args, "rule", []),
            profiles=args.profile,
            areas=args.area,
            snapshot=snapshot,
        )
    except ValueError as exc:
        routing_invalid = True
        result = invalid_context_result(
            supplied_task=args.task,
            supplied_paths=getattr(args, "path", []),
            rules=getattr(args, "rule", []),
            profiles=args.profile,
            areas=args.area,
            error=exc,
        )
    overlay = LocalOverlay(LocalStatus.DISABLED, Path("."), "")
    if not routing_invalid and not getattr(args, "no_local", False):
        try:
            # Local state is project-scoped and must never be selected from a
            # permissively parsed legacy/invalid manifest.  A valid shared
            # routing result may still represent a pre-metadata project, in
            # which case local overlay loading remains disabled.
            overlay_project_id = validated_project_identity(
                memory_dir,
                manifest_text=snapshot.manifest_text,
                allow_legacy_entry_schema=not args.strict_routing,
            )
        except (OSError, ValueError):
            overlay_project_id = None
        if overlay_project_id is not None:
            overlay = inspect_overlay(
                project_root,
                overlay_project_id,
                shared_ids={entry.entry_id for entry in snapshot.relation_entries},
                entry_schema_version=snapshot.entry_schema_version,
            )
    local_contents: list[tuple[str, str]] = []
    local_scope_warnings: list[str] = []
    if overlay.status == LocalStatus.BOUND:
        # ``inspect_overlay`` captured and validated the local modules above.
        # Consume only that immutable view: reopening a private module here
        # would allow a replacement between validation and rendering to mix
        # inputs from two different local states.
        for captured in overlay.captured_modules:
            text = captured.text
            entries = captured.entries
            if any(entry.scope not in {"local-user", "local-machine"} for entry in entries):
                local_scope_warnings.append(
                    f"Local module {captured.path.name} contains a non-local Scope and was excluded."
                )
                continue
            local_contents.append((f"local/{captured.relative}", text.strip()))
    completeness = result.completeness
    if (
        completeness == RoutingCompleteness.COMPLETE
        and (overlay.status == LocalStatus.REVIEW or local_scope_warnings)
    ):
        completeness = RoutingCompleteness.INCOMPLETE
    matched_areas = tuple(
        module.module_id.removeprefix("areas/").removesuffix(".md")
        for module in result.modules
        if module.loaded and module.module_id.startswith("areas/")
    )
    conflicts = (
        ConflictResult(ConflictStatus.INVALID, ())
        if routing_invalid
        else analyze_snapshot(
            snapshot,
            matched_areas=matched_areas,
            included_modules=tuple(module.module_id for module in result.modules if module.loaded),
        )
    )

    _render_header(result, completeness)
    if completeness != result.completeness:
        print(f"Shared routing completeness: {result.completeness.value}")
    render_overlay_status(overlay)
    if local_contents:
        print("Local loaded:")
        for name, _text in local_contents:
            print(f"- {name}")
            if args.explain:
                print("  Precedence: below shared constraints, tombstones, decisions, and rules")
    _render_modules(result, explain=args.explain)
    if args.explain:
        print("Policy exclusions:")
        print("- inbox.md: candidate/maintenance-only; excluded from normal task context")
        print("- archive/: explicit maintenance only; archive files were not enumerated")
        print("Incomplete dimensions:")
        dimensions = [*result.incomplete_dimensions]
        if overlay.status == LocalStatus.REVIEW:
            dimensions.append("local-overlay-review")
        if local_scope_warnings:
            dimensions.append("invalid-local-scope")
        for dimension in dict.fromkeys(dimensions) or ("none",):
            print(f"- {dimension}")
    print("Budget omissions:")
    if result.omissions:
        for omission in result.omissions:
            print(f"- {omission.unit_ref}")
            if args.explain:
                print(f"  Module: {omission.module_id}")
                print(f"  Disposition: {omission.disposition}")
                print(f"  Reason: {omission.reason.value}")
    else:
        print("- none")
    oversized = [item for item in result.modules if item.oversized]
    if oversized:
        print("Oversized atomic entries:")
        for module in oversized:
            print(f"- {module.module_id}: one atomic entry exceeds the {budget_for(module.module_id)}-token budget and was included whole")
    render_conflict_result(conflicts)
    render_warnings = list(result.warnings)
    if migration_required:
        render_warnings.append(ENTRY_SCHEMA_MIGRATION_MESSAGE)
    if render_warnings:
        print("Warnings:")
        for warning in render_warnings:
            print(f"- {warning}")
    if routing_invalid:
        print(f"Error: {result.warnings[0]}", file=sys.stderr)
    for warning in local_scope_warnings:
        print(f"Warning: {warning}")

    rejected = False
    if args.strict_routing:
        rejected = (
            migration_required
            or completeness != RoutingCompleteness.COMPLETE
            or conflicts.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}
        )
        if conflicts.status == ConflictStatus.REVIEW and result.canonical_task in {"planning", "implementation", "artifact", "history"}:
            rejected = True
        if rejected:
            print("Context pack not approved for substantial work")
            print(
                f"Strict routing rejected context: completeness={completeness.value}, conflict={conflicts.status.value}",
                file=sys.stderr,
            )
    elif not routing_invalid and conflicts.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}:
        print("Context pack contains unresolved active-memory conflict")

    # A strict read that failed the structural gate must never present an
    # invalid module as a usable context pack.  Conflict diagnostics above
    # remain available, while safe metadata and routing dispositions are
    # still rendered for inspection.
    if not args.names_only and not (
        args.strict_routing
        and (migration_required or conflicts.status == ConflictStatus.INVALID)
    ):
        for name, text in result.contents:
            print(f"\n## {name}\n")
            print(text)

    if args.strict_routing and rejected:
        if completeness == RoutingCompleteness.INCOMPLETE and conflicts.status not in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}:
            return 1
        return 2
    if not args.names_only and not (
        args.strict_routing
        and (migration_required or conflicts.status == ConflictStatus.INVALID)
    ):
        for name, text in local_contents:
            print(f"\n## {name}\n")
            print(text)

    if completeness == RoutingCompleteness.AMBIGUOUS:
        return 1
    if completeness == RoutingCompleteness.INVALID:
        return 2
    if conflicts.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}:
        return 2
    return 0
