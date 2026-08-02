"""Render a deterministic and explainable MemoryCustodian context pack."""

from __future__ import annotations

from pathlib import Path
import sys

from .conflicts import ConflictResult, ConflictStatus, analyze_conflicts, render_conflict_result
from .context import ContextRoutingResult, invalid_context_result, route_context
from .entries import parse_structured_entries
from .local_overlay import LocalOverlay, LocalStatus, inspect_overlay, project_identity, render_overlay_status
from .protocol import budget_for, resolve_memory_dir, resolve_project_root
from .routes import ModuleDisposition, RouteReason, RoutedModule, RoutingCompleteness


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
    overlay = (
        LocalOverlay(LocalStatus.DISABLED, Path("."), "")
        if routing_invalid
        else inspect_overlay(
            project_root,
            project_identity(memory_dir),
            disabled=getattr(args, "no_local", False),
        )
    )
    local_contents: list[tuple[str, str]] = []
    local_scope_warnings: list[str] = []
    if overlay.status in {LocalStatus.BOUND, LocalStatus.REVIEW}:
        for path in overlay.modules:
            text = path.read_text(encoding="utf-8")
            entries = parse_structured_entries(path, text)
            if any(entry.scope not in {"local-user", "local-machine"} for entry in entries):
                local_scope_warnings.append(
                    f"Local module {path.name} contains a non-local Scope and was excluded."
                )
                continue
            local_contents.append((f"local/{path.relative_to(overlay.directory).as_posix()}", text.strip()))
    completeness = result.completeness
    if overlay.status == LocalStatus.REVIEW or local_scope_warnings:
        completeness = RoutingCompleteness.INCOMPLETE
    matched_areas = tuple(
        module.module_id.removeprefix("areas/").removesuffix(".md")
        for module in result.modules
        if module.loaded and module.module_id.startswith("areas/")
    )
    conflicts = (
        ConflictResult(ConflictStatus.INVALID, ())
        if routing_invalid
        else analyze_conflicts(
            memory_dir,
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
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    if routing_invalid:
        print(f"Error: {result.warnings[0]}", file=sys.stderr)
    for warning in local_scope_warnings:
        print(f"Warning: {warning}")

    rejected = False
    if args.strict_routing:
        rejected = (
            completeness != RoutingCompleteness.COMPLETE
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

    if not args.names_only:
        for name, text in result.contents:
            print(f"\n## {name}\n")
            print(text)

    if args.strict_routing and rejected:
        if completeness == RoutingCompleteness.INCOMPLETE and conflicts.status not in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}:
            return 1
        return 2
    if not args.names_only:
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
