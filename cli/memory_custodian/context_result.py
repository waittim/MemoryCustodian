"""Shared construction and rendering of one immutable context-pack result.

``read`` and invocation ``audit`` must describe the same final context bytes.
This module owns that boundary: routing, local-overlay capture, conflict
selection, strict-routing approval, deterministic rendering, and hashing all
consume one supplied :class:`~memory_custodian.snapshot.MemorySnapshot`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from .conflicts import ConflictResult, ConflictStatus, analyze_snapshot
from .context import ContextRoutingResult, invalid_context_result, route_context
from .local_overlay import (
    LocalOverlay,
    LocalStatus,
    inspect_overlay,
    validated_project_identity,
)
from .protocol import ENTRY_SCHEMA_MIGRATION_MESSAGE, budget_for
from .routes import ModuleDisposition, RouteReason, RoutedModule, RoutingCompleteness
from .snapshot import MemorySnapshot, build_snapshot


@dataclass(frozen=True)
class ContextResult:
    """The complete result of one context invocation over immutable inputs."""

    project_root: Path
    memory_dir: Path
    snapshot: MemorySnapshot
    routing: ContextRoutingResult
    overlay: LocalOverlay
    local_contents: tuple[tuple[str, str], ...]
    local_scope_warnings: tuple[str, ...]
    completeness: RoutingCompleteness
    conflicts: ConflictResult
    migration_required: bool
    routing_invalid: bool
    strict_routing: bool
    rejected: bool
    return_code: int


def normalize_context_text(text: str) -> str:
    """Return canonical LF context text with a terminal newline."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def context_sha256(text: str) -> str:
    """Hash the canonical UTF-8/LF rendering of a context pack."""

    return hashlib.sha256(normalize_context_text(text).encode("utf-8")).hexdigest()


def build_context_result(
    project_root: Path,
    memory_dir: Path,
    *,
    supplied_task: str,
    supplied_paths: list[str] | tuple[str, ...] = (),
    rules: list[str] | tuple[str, ...] = (),
    profiles: list[str] | tuple[str, ...] = (),
    areas: list[str] | tuple[str, ...] = (),
    strict_routing: bool = False,
    no_local: bool = False,
    snapshot: MemorySnapshot | None = None,
    captured_overlay: LocalOverlay | None = None,
    router: Callable[..., ContextRoutingResult] = route_context,
    overlay_inspector: Callable[..., LocalOverlay] = inspect_overlay,
    identity_validator: Callable[..., str] = validated_project_identity,
    conflict_analyzer: Callable[..., ConflictResult] = analyze_snapshot,
) -> ContextResult:
    """Build one context result without reopening captured shared/local files."""

    snapshot = snapshot or build_snapshot(memory_dir, project_root)
    migration_required = snapshot.manifest_contract.migration_available
    routing_invalid = False
    try:
        routing = router(
            project_root,
            memory_dir,
            supplied_task=supplied_task,
            supplied_paths=supplied_paths,
            rules=rules,
            profiles=profiles,
            areas=areas,
            snapshot=snapshot,
        )
    except ValueError as exc:
        routing_invalid = True
        routing = invalid_context_result(
            supplied_task=supplied_task,
            supplied_paths=supplied_paths,
            rules=rules,
            profiles=profiles,
            areas=areas,
            error=exc,
        )

    overlay = LocalOverlay(LocalStatus.DISABLED, Path("."), "")
    if not routing_invalid and not no_local:
        try:
            project_id = identity_validator(
                memory_dir,
                manifest_text=snapshot.manifest_text,
                allow_legacy_entry_schema=not strict_routing,
            )
        except (OSError, ValueError):
            project_id = None
        if project_id is not None:
            if captured_overlay is not None and captured_overlay.project_id == project_id:
                overlay = captured_overlay
            else:
                overlay = overlay_inspector(
                    project_root,
                    project_id,
                    shared_ids={entry.entry_id for entry in snapshot.relation_entries},
                    entry_schema_version=snapshot.entry_schema_version,
                )

    local_contents: list[tuple[str, str]] = []
    local_scope_warnings: list[str] = []
    if overlay.status == LocalStatus.BOUND:
        for captured in overlay.captured_modules:
            if any(
                entry.scope not in {"local-user", "local-machine"}
                for entry in captured.entries
            ):
                local_scope_warnings.append(
                    f"Local module {captured.path.name} contains a non-local Scope and was excluded."
                )
                continue
            local_contents.append((f"local/{captured.relative}", captured.text.strip()))

    completeness = routing.completeness
    if (
        completeness == RoutingCompleteness.COMPLETE
        and (overlay.status == LocalStatus.REVIEW or local_scope_warnings)
    ):
        completeness = RoutingCompleteness.INCOMPLETE

    matched_areas = tuple(
        module.module_id.removeprefix("areas/").removesuffix(".md")
        for module in routing.modules
        if module.loaded and module.module_id.startswith("areas/")
    )
    conflicts = (
        ConflictResult(ConflictStatus.INVALID, ())
        if routing_invalid
        else conflict_analyzer(
            snapshot,
            matched_areas=matched_areas,
            included_modules=tuple(
                module.module_id for module in routing.modules if module.loaded
            ),
        )
    )

    rejected = False
    if strict_routing:
        rejected = (
            migration_required
            or completeness != RoutingCompleteness.COMPLETE
            or conflicts.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}
        )
        if (
            conflicts.status == ConflictStatus.REVIEW
            and routing.canonical_task
            in {"planning", "implementation", "artifact", "history"}
        ):
            rejected = True

    if strict_routing and rejected:
        return_code = (
            1
            if completeness == RoutingCompleteness.INCOMPLETE
            and conflicts.status not in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}
            else 2
        )
    elif completeness == RoutingCompleteness.AMBIGUOUS:
        return_code = 1
    elif completeness == RoutingCompleteness.INVALID:
        return_code = 2
    elif conflicts.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}:
        return_code = 2
    else:
        return_code = 0

    return ContextResult(
        project_root,
        memory_dir,
        snapshot,
        routing,
        overlay,
        tuple(local_contents),
        tuple(local_scope_warnings),
        completeness,
        conflicts,
        migration_required,
        routing_invalid,
        strict_routing,
        rejected,
        return_code,
    )


def _reason(module: RoutedModule) -> str:
    primary = next(
        (
            item
            for item in (
                RouteReason.INVALID,
                RouteReason.MISSING_REQUIRED,
                RouteReason.OPTIONAL_ABSENT,
            )
            if item in module.reasons
        ),
        next(
            (
                item
                for item in module.reasons
                if item != RouteReason.BUDGET_OMISSION
            ),
            module.reasons[0],
        ),
    )
    detail = f" ({'; '.join(module.details)})" if module.details else ""
    return primary.value + detail


def _render_modules(
    stream: StringIO,
    result: ContextRoutingResult,
    *,
    explain: bool,
) -> None:
    groups = (
        ("Loaded", ModuleDisposition.LOADED),
        ("Skipped optional", ModuleDisposition.SKIPPED),
        ("Missing required", ModuleDisposition.MISSING_REQUIRED),
        ("Missing optional", ModuleDisposition.MISSING_OPTIONAL),
        ("Invalid", ModuleDisposition.INVALID),
    )
    for heading, disposition in groups:
        matches = [item for item in result.modules if item.disposition == disposition]
        print(f"{heading}:", file=stream)
        if not matches:
            print("- none", file=stream)
        for module in matches:
            print(f"- {module.module_id}", file=stream)
            if not explain:
                continue
            print(f"  Disposition: {module.disposition.value}", file=stream)
            print(f"  Reason: {_reason(module)}", file=stream)
            if RouteReason.CANONICAL_TASK in module.reasons:
                print(f"  Matching input: task:{result.canonical_task}", file=stream)
            elif RouteReason.EXPLICIT_RULE in module.reasons:
                name = module.module_id.removeprefix("rules/").removesuffix(".md")
                print(f"  Matching input: rule:{name}", file=stream)
            elif RouteReason.EXPLICIT_PROFILE in module.reasons:
                name = module.module_id.removeprefix("profiles/").removesuffix(".md")
                print(f"  Matching input: profile:{name}", file=stream)
            elif RouteReason.EXPLICIT_AREA in module.reasons:
                name = module.module_id.removeprefix("areas/").removesuffix(".md")
                print(f"  Matching input: area:{name}", file=stream)


def _render_conflicts(stream: StringIO, result: ConflictResult) -> None:
    print(f"Conflict status: {result.status.value}", file=stream)
    for finding in result.findings:
        identity = ""
        if finding.subject_id or finding.facet or finding.scopes:
            identity = (
                f" [Subject: {finding.subject_id or '-'}; "
                f"Facet: {finding.facet or '-'}; "
                f"Scope: {', '.join(finding.scopes) or '-'}]"
            )
        entries = (
            f" Entries: {', '.join(finding.entry_ids)}."
            if finding.entry_ids
            else ""
        )
        print(
            f"- {finding.code} {finding.status.value}: "
            f"{finding.message}{identity}{entries}",
            file=stream,
        )


def render_context_result(
    context: ContextResult,
    *,
    explain: bool = False,
    names_only: bool = False,
) -> str:
    """Render the exact context text shared by ``read`` and invocation audit."""

    result = context.routing
    stream = StringIO()
    print("# Memory Context Pack", file=stream)
    print(f"Task: {result.supplied_task}", file=stream)
    print(f"Canonical task: {result.canonical_task}", file=stream)
    print("Paths:", file=stream)
    if result.paths:
        for path in result.paths:
            suffix = " (missing-on-disk)" if path.missing_on_disk else ""
            print(f"- {path.value}{suffix}", file=stream)
    else:
        print("- none supplied", file=stream)
    print("Explicit scope:", file=stream)
    explicit = [
        *(f"rule:{item}" for item in result.explicit_rules),
        *(f"profile:{item}" for item in result.explicit_profiles),
        *(f"area:{item}" for item in result.explicit_areas),
    ]
    for value in explicit or ["none supplied"]:
        print(f"- {value}", file=stream)
    print(f"Routing completeness: {context.completeness.value}", file=stream)
    if context.completeness != result.completeness:
        print(f"Shared routing completeness: {result.completeness.value}", file=stream)

    print(f"Local overlay status: {context.overlay.status.value}", file=stream)
    for warning in context.overlay.warnings:
        print(f"- {warning}", file=stream)
    if context.local_contents:
        print("Local loaded:", file=stream)
        for name, _text in context.local_contents:
            print(f"- {name}", file=stream)
            if explain:
                print(
                    "  Precedence: below shared constraints, tombstones, decisions, and rules",
                    file=stream,
                )

    _render_modules(stream, result, explain=explain)
    if explain:
        print("Policy exclusions:", file=stream)
        print(
            "- inbox.md: candidate/maintenance-only; excluded from normal task context",
            file=stream,
        )
        print(
            "- archive/: explicit maintenance only; archive files were not enumerated",
            file=stream,
        )
        print("Incomplete dimensions:", file=stream)
        dimensions = [*result.incomplete_dimensions]
        if context.overlay.status == LocalStatus.REVIEW:
            dimensions.append("local-overlay-review")
        if context.local_scope_warnings:
            dimensions.append("invalid-local-scope")
        for dimension in dict.fromkeys(dimensions) or ("none",):
            print(f"- {dimension}", file=stream)

    print("Budget omissions:", file=stream)
    if result.omissions:
        for omission in result.omissions:
            print(f"- {omission.unit_ref}", file=stream)
            if explain:
                print(f"  Module: {omission.module_id}", file=stream)
                print(f"  Disposition: {omission.disposition}", file=stream)
                print(f"  Reason: {omission.reason.value}", file=stream)
    else:
        print("- none", file=stream)

    oversized = [item for item in result.modules if item.oversized]
    if oversized:
        print("Oversized atomic entries:", file=stream)
        for module in oversized:
            print(
                f"- {module.module_id}: one atomic entry exceeds the "
                f"{budget_for(module.module_id)}-token budget and was included whole",
                file=stream,
            )

    _render_conflicts(stream, context.conflicts)
    render_warnings = list(result.warnings)
    if context.migration_required:
        render_warnings.append(ENTRY_SCHEMA_MIGRATION_MESSAGE)
    if render_warnings:
        print("Warnings:", file=stream)
        for warning in render_warnings:
            print(f"- {warning}", file=stream)
    for warning in context.local_scope_warnings:
        print(f"Warning: {warning}", file=stream)

    if context.strict_routing and context.rejected:
        print("Context pack not approved for substantial work", file=stream)
    elif (
        not context.routing_invalid
        and context.conflicts.status
        in {ConflictStatus.CONFLICT, ConflictStatus.INVALID}
    ):
        print("Context pack contains unresolved active-memory conflict", file=stream)

    suppress_shared = (
        context.strict_routing
        and (
            context.migration_required
            or context.conflicts.status == ConflictStatus.INVALID
        )
    )
    if not names_only and not suppress_shared:
        for name, text in result.contents:
            print(f"\n## {name}\n", file=stream)
            print(text, file=stream)

    if (
        not (context.strict_routing and context.rejected)
        and not names_only
        and not suppress_shared
    ):
        for name, text in context.local_contents:
            print(f"\n## {name}\n", file=stream)
            print(text, file=stream)

    return normalize_context_text(stream.getvalue())


def module_invocation_data(context: ContextResult) -> list[dict[str, Any]]:
    """Return the stable legacy invocation module view from the shared result."""

    return [
        {
            "module_id": item.module_id,
            "required": item.required,
            "loaded": item.loaded,
            "disposition": item.disposition.value if item.disposition else None,
            "reasons": [reason.value for reason in item.reasons],
            "details": list(item.details),
        }
        for item in sorted(
            context.routing.modules,
            key=lambda item: item.module_id.casefold(),
        )
    ]
