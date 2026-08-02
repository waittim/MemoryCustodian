"""Shared deterministic context routing and disposition model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re

from .protocol import (
    budget_for,
    estimate_tokens,
    manifest_task_modules,
    parse_markdown_units,
    protocol_metadata,
    render_markdown_document,
    resolve_manifest_memory_path,
)
from .routes import (
    ModuleDeclaration,
    ModuleDisposition,
    NormalizedPath,
    RouteReason,
    RoutedModule,
    RoutingCompleteness,
    SUBSTANTIAL_TASKS,
    canonical_task,
    glob_matches,
    merge_routed_modules,
    normalize_input_path,
    parse_optional_module_index,
)


@dataclass(frozen=True)
class BudgetOmission:
    module_id: str
    unit_ref: str
    disposition: str = "omitted-by-budget"
    reason: RouteReason = RouteReason.BUDGET_OMISSION


@dataclass(frozen=True)
class ContextRoutingResult:
    supplied_task: str
    canonical_task: str
    paths: tuple[NormalizedPath, ...]
    explicit_rules: tuple[str, ...]
    explicit_profiles: tuple[str, ...]
    explicit_areas: tuple[str, ...]
    completeness: RoutingCompleteness
    modules: tuple[RoutedModule, ...]
    contents: tuple[tuple[str, str], ...]
    omissions: tuple[BudgetOmission, ...]
    warnings: tuple[str, ...]
    incomplete_dimensions: tuple[str, ...]


def invalid_context_result(
    *,
    supplied_task: str,
    supplied_paths: list[str] | tuple[str, ...],
    rules: list[str] | tuple[str, ...],
    profiles: list[str] | tuple[str, ...],
    areas: list[str] | tuple[str, ...],
    error: ValueError,
) -> ContextRoutingResult:
    """Represent invalid routing through the same result model as valid reads."""

    try:
        canonical = canonical_task(supplied_task)
    except ValueError:
        canonical = "<invalid>"
    paths = tuple(
        NormalizedPath(str(value).replace("\\", "/"), False)
        for value in supplied_paths
    )
    invalid = RoutedModule(
        "manifest.md",
        True,
        (RouteReason.INVALID,),
        disposition=ModuleDisposition.INVALID,
        details=(str(error),),
    )
    return ContextRoutingResult(
        supplied_task,
        canonical,
        paths,
        tuple(rules),
        tuple(profiles),
        tuple(areas),
        RoutingCompleteness.INVALID,
        (invalid,),
        (),
        (),
        (f"Routing input or manifest is invalid: {error}",),
        ("invalid-routing",),
    )


def _requested(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        candidate = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", candidate):
            raise ValueError(f"Invalid explicit module name: {value}")
        normalized.append(candidate)
    return tuple(sorted(dict.fromkeys(normalized)))


def _reason_for(declaration: ModuleDeclaration, *, explicit: bool, path_match: bool, task_match: bool) -> RouteReason:
    if explicit and declaration.module_type == "rules":
        return RouteReason.EXPLICIT_RULE
    if explicit and declaration.module_type == "profiles":
        return RouteReason.EXPLICIT_PROFILE
    if explicit and declaration.module_type == "areas":
        return RouteReason.EXPLICIT_AREA
    if path_match:
        return RouteReason.PATH_MATCH
    if task_match:
        return RouteReason.CANONICAL_TASK
    raise AssertionError("route reason requested for inactive declaration")


def _optional_route(
    declaration: ModuleDeclaration,
    task: str,
    paths: tuple[NormalizedPath, ...],
    explicit: set[str],
) -> RoutedModule:
    requested = declaration.slug in explicit
    task_match = "task" in declaration.activation and task in declaration.tasks
    matches = tuple(
        f"{path.value} <- {pattern}"
        for path in paths
        for pattern in declaration.paths
        if glob_matches(pattern, path.value)
    )
    path_match = bool(matches)
    explicit_allowed = declaration.activation in {"explicit-only", "task-or-explicit", "path-or-explicit"}
    active = task_match or path_match or (requested and explicit_allowed)
    if active:
        return RoutedModule(
            declaration.module_id,
            False,
            (_reason_for(declaration, explicit=requested and explicit_allowed, path_match=path_match, task_match=task_match),),
            details=matches,
        )
    if declaration.module_type == "rules" and "task" in declaration.activation:
        reason = RouteReason.TASK_MISMATCH
    elif declaration.module_type == "areas" and "path" in declaration.activation:
        reason = RouteReason.SCOPE_MISSING if not paths else RouteReason.NO_PATH_MATCH
    else:
        reason = RouteReason.NOT_REQUESTED
    return RoutedModule(
        declaration.module_id,
        False,
        (reason,),
        disposition=ModuleDisposition.SKIPPED,
    )


def _unit_ref(module_id: str, text: str, ordinal: int) -> str:
    first = text.splitlines()[0] if text.splitlines() else ""
    match = re.search(r"\bMC-(?:DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-\d{8}-[0-9a-f]{8}\b", first, re.I)
    return match.group(0) if match else f"{module_id}#unit-{ordinal}"


def _pack(module_id: str, text: str, budget: int | None) -> tuple[str, tuple[BudgetOmission, ...], bool]:
    normalized = text.strip()
    if budget is None or estimate_tokens(normalized) <= budget:
        return normalized, (), False
    document = parse_markdown_units(normalized)
    chosen = []
    oversized = False
    stop = len(document.units)
    for index, unit in enumerate(document.units):
        candidate = render_markdown_document(document, [*chosen, unit]).strip()
        if estimate_tokens(candidate) <= budget:
            chosen.append(unit)
            continue
        first_semantic = unit.kind != "preamble" and not any(item.kind != "preamble" for item in chosen)
        if not chosen or first_semantic:
            chosen.append(unit)
            oversized = True
            stop = index + 1
        else:
            stop = index
        break
    omissions = tuple(
        BudgetOmission(module_id, _unit_ref(module_id, unit.text, index + 1))
        for index, unit in enumerate(document.units[stop:], start=stop)
        if unit.kind != "preamble"
    )
    return render_markdown_document(document, chosen).strip(), omissions, oversized


def route_context(
    project_root: Path,
    memory_dir: Path,
    *,
    supplied_task: str,
    supplied_paths: list[str] | tuple[str, ...] = (),
    rules: list[str] | tuple[str, ...] = (),
    profiles: list[str] | tuple[str, ...] = (),
    areas: list[str] | tuple[str, ...] = (),
) -> ContextRoutingResult:
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    manifest = manifest_path.read_text(encoding="utf-8")
    canonical = canonical_task(supplied_task)
    normalized_by_value = {
        item.value: item
        for item in (normalize_input_path(project_root, value) for value in supplied_paths)
    }
    normalized_paths = tuple(normalized_by_value[key] for key in sorted(normalized_by_value))
    requested = {
        "rules": _requested(rules),
        "profiles": _requested(profiles),
        "areas": _requested(areas),
    }
    version = protocol_metadata(manifest).get("protocol_version", "0.5")
    declarations = parse_optional_module_index(manifest, legacy_compatible=version != "0.7")
    declared_slugs = {
        kind: {item.slug for item in declarations if item.module_type == kind}
        for kind in ("rules", "profiles", "areas")
    }
    warnings: list[str] = []
    incomplete: list[str] = []
    missing_explicit: list[RoutedModule] = []
    for kind, values in requested.items():
        for slug in values:
            if slug not in declared_slugs[kind]:
                singular = kind[:-1]
                warnings.append(f"Explicit {singular} {slug!r} is not enabled in the manifest.")
                missing_explicit.append(RoutedModule(
                    f"{kind}/{slug}.md", False,
                    ({"rules": RouteReason.EXPLICIT_RULE, "profiles": RouteReason.EXPLICIT_PROFILE, "areas": RouteReason.EXPLICIT_AREA}[kind], RouteReason.OPTIONAL_ABSENT),
                    disposition=ModuleDisposition.MISSING_OPTIONAL,
                ))

    path_routed = [
        item for item in declarations
        if item.module_type == "areas" and "path" in item.activation
    ]
    if canonical in SUBSTANTIAL_TASKS and path_routed and not normalized_paths and not requested["areas"]:
        incomplete.append("area-path-scope")
        warnings.append(
            "Enabled path-routed areas were not evaluated because no paths or explicit areas were supplied."
        )

    base = manifest_task_modules(memory_dir, supplied_task)
    optional = [
        _optional_route(
            declaration,
            canonical,
            normalized_paths,
            set(requested[declaration.module_type]),
        )
        for declaration in declarations
    ]
    modules = merge_routed_modules([*base, *optional, *missing_explicit])
    results: list[RoutedModule] = []
    contents: list[tuple[str, str]] = []
    omissions: list[BudgetOmission] = []
    for module in modules:
        if module.disposition == ModuleDisposition.SKIPPED:
            results.append(module)
            continue
        if module.disposition == ModuleDisposition.MISSING_OPTIONAL and RouteReason.OPTIONAL_ABSENT in module.reasons:
            results.append(module)
            continue
        path = resolve_manifest_memory_path(memory_dir, module.module_id)
        if not path.exists():
            results.append(module.with_result(loaded=False, absent=True))
            continue
        packed, module_omissions, oversized = _pack(
            module.module_id, path.read_text(encoding="utf-8"), budget_for(module.module_id)
        )
        contents.append((module.module_id, packed))
        omissions.extend(module_omissions)
        results.append(module.with_result(
            loaded=True,
            omitted_entries=len(module_omissions),
            oversized=oversized,
        ))

    if any(item.disposition == ModuleDisposition.MISSING_REQUIRED for item in results):
        incomplete.append("required-module-missing")
        warnings.append("One or more required routed modules are missing.")
    completeness = RoutingCompleteness.INCOMPLETE if incomplete else RoutingCompleteness.COMPLETE
    if any(item.disposition == ModuleDisposition.INVALID for item in results):
        completeness = RoutingCompleteness.INVALID
    return ContextRoutingResult(
        supplied_task,
        canonical,
        normalized_paths,
        requested["rules"],
        requested["profiles"],
        requested["areas"],
        completeness,
        tuple(results),
        tuple(contents),
        tuple(omissions),
        tuple(warnings),
        tuple(incomplete),
    )
