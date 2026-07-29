"""Structured routing provenance and stable module identity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import PurePosixPath
import re


class RouteReason(str, Enum):
    ALWAYS_LOAD = "always-load"
    CANONICAL_TASK = "canonical-task-route"
    EXPLICIT_PROFILE = "explicit-profile"
    EXPLICIT_AREA = "explicit-area"
    OPTIONAL_ABSENT = "optional-file-absent"
    BUDGET_OMISSION = "budget-omission"


@dataclass(frozen=True)
class RoutedModule:
    module_id: str
    required: bool
    reasons: tuple[RouteReason, ...]
    loaded: bool = False
    omitted_entries: int = 0
    oversized: bool = False

    def with_result(
        self,
        *,
        loaded: bool,
        absent: bool = False,
        omitted_entries: int = 0,
        oversized: bool = False,
    ) -> "RoutedModule":
        reasons = list(self.reasons)
        if absent and not self.required:
            reasons.append(RouteReason.OPTIONAL_ABSENT)
        if omitted_entries:
            reasons.append(RouteReason.BUDGET_OMISSION)
        return replace(
            self,
            loaded=loaded,
            omitted_entries=omitted_entries,
            oversized=oversized,
            reasons=tuple(dict.fromkeys(reasons)),
        )


def normalize_module_identity(value: str) -> str:
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:", raw)
        or ".." in path.parts
        or path.suffix != ".md"
    ):
        raise ValueError(f"unsafe or malformed memory path {value!r}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ValueError(f"unsafe or malformed memory path {value!r}")
    return normalized


def merge_routed_modules(modules: list[RoutedModule]) -> list[RoutedModule]:
    merged: dict[str, RoutedModule] = {}
    order: list[str] = []
    for module in modules:
        module_id = normalize_module_identity(module.module_id)
        normalized = replace(module, module_id=module_id)
        if module_id not in merged:
            order.append(module_id)
            merged[module_id] = normalized
            continue
        previous = merged[module_id]
        merged[module_id] = replace(
            previous,
            required=previous.required or normalized.required,
            reasons=tuple(dict.fromkeys([*previous.reasons, *normalized.reasons])),
        )
    return [merged[module_id] for module_id in order]
