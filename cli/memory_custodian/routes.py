"""Protocol 0.7 deterministic routing primitives.

The manifest is the only shared routing authority.  This module deliberately
contains no task-text classifier, filesystem search, or semantic matcher.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath
import re


CANONICAL_TASKS = (
    "general",
    "planning",
    "implementation",
    "artifact",
    "preferences",
    "history",
    "maintenance",
)

TASK_ALIASES = {
    "default": "general",
    "general": "general",
    "planning": "planning",
    "architecture": "planning",
    "refactoring": "planning",
    "implementation": "implementation",
    "execution": "implementation",
    "debugging": "implementation",
    "review": "implementation",
    "artifact": "artifact",
    "output": "artifact",
    "preferences": "preferences",
    "recap": "history",
    "history": "history",
    "status": "history",
    "maintenance": "maintenance",
    "compact": "maintenance",
    "forget": "maintenance",
}

# Reserved Protocol 0.7 compatibility aliases are accepted inputs but do not
# silently choose one canonical interpretation. Default manifests define no
# mutually-exclusive route policy, so this explicit table is the normative
# reachable AMBIGUOUS case.
AMBIGUOUS_TASK_ALIASES = {
    "development": ("planning", "implementation"),
}
TASK_INPUTS = tuple(sorted((*TASK_ALIASES, *AMBIGUOUS_TASK_ALIASES)))

SUBSTANTIAL_TASKS = frozenset({"planning", "implementation", "artifact", "history"})


class RoutingCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


class RouteReason(str, Enum):
    ALWAYS_LOAD = "MC-ROUTE-ALWAYS"
    CANONICAL_TASK = "MC-ROUTE-TASK"
    PATH_MATCH = "MC-ROUTE-PATH"
    EXPLICIT_AREA = "MC-ROUTE-EXPLICIT-AREA"
    EXPLICIT_PROFILE = "MC-ROUTE-EXPLICIT-PROFILE"
    EXPLICIT_RULE = "MC-ROUTE-EXPLICIT-RULE"
    TASK_MISMATCH = "MC-SKIP-TASK-MISMATCH"
    NO_PATH_MATCH = "MC-SKIP-NO-PATH-MATCH"
    NOT_REQUESTED = "MC-SKIP-NOT-REQUESTED"
    SCOPE_MISSING = "MC-SKIP-SCOPE-MISSING"
    MISSING_REQUIRED = "MC-MISSING-REQUIRED"
    OPTIONAL_ABSENT = "MC-MISSING-OPTIONAL"
    BUDGET_OMISSION = "MC-OMIT-BUDGET"
    AMBIGUOUS = "MC-ROUTE-AMBIGUOUS"
    INVALID = "MC-ROUTE-INVALID"


class ModuleDisposition(str, Enum):
    LOADED = "loaded"
    SKIPPED = "skipped"
    MISSING_REQUIRED = "missing-required"
    MISSING_OPTIONAL = "missing-optional"
    INVALID = "invalid"


@dataclass(frozen=True)
class ModuleDeclaration:
    module_id: str
    module_type: str
    activation: str
    tasks: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    description: str = ""

    @property
    def slug(self) -> str:
        return PurePosixPath(self.module_id).stem


@dataclass(frozen=True)
class NormalizedPath:
    value: str
    missing_on_disk: bool


@dataclass(frozen=True)
class RoutedModule:
    module_id: str
    required: bool
    reasons: tuple[RouteReason, ...]
    loaded: bool = False
    omitted_entries: int = 0
    oversized: bool = False
    disposition: ModuleDisposition | None = None
    details: tuple[str, ...] = ()

    def with_result(
        self,
        *,
        loaded: bool,
        absent: bool = False,
        omitted_entries: int = 0,
        oversized: bool = False,
        disposition: ModuleDisposition | None = None,
        details: tuple[str, ...] = (),
    ) -> "RoutedModule":
        reasons = list(self.reasons)
        if absent:
            reasons.append(
                RouteReason.MISSING_REQUIRED if self.required else RouteReason.OPTIONAL_ABSENT
            )
        if omitted_entries:
            reasons.append(RouteReason.BUDGET_OMISSION)
        if disposition is None:
            if loaded:
                disposition = ModuleDisposition.LOADED
            elif absent and self.required:
                disposition = ModuleDisposition.MISSING_REQUIRED
            elif absent:
                disposition = ModuleDisposition.MISSING_OPTIONAL
            else:
                disposition = ModuleDisposition.SKIPPED
        return replace(
            self,
            loaded=loaded,
            omitted_entries=omitted_entries,
            oversized=oversized,
            disposition=disposition,
            reasons=tuple(dict.fromkeys(reasons)),
            details=details or self.details,
        )


def canonical_task(value: str) -> str:
    try:
        return TASK_ALIASES[value.casefold()]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"Unsupported task route: {value}") from exc


def task_interpretations(value: str) -> tuple[str, ...]:
    try:
        normalized = value.casefold()
    except AttributeError as exc:
        raise ValueError(f"Unsupported task route: {value}") from exc
    if normalized in AMBIGUOUS_TASK_ALIASES:
        return AMBIGUOUS_TASK_ALIASES[normalized]
    return (canonical_task(normalized),)


def normalize_module_identity(value: str) -> str:
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:", raw)
        or any(part in {"", ".", ".."} for part in raw.split("/"))
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
            details=tuple(dict.fromkeys([*previous.details, *normalized.details])),
        )
    return [merged[module_id] for module_id in order]


_MODULE_LINE_RE = re.compile(r"^- `([^`]+)`(?:\s*:\s*(.*))?$")
_META_LINE_RE = re.compile(r"^  - ([a-z-]+):\s*(.*)$")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_ALLOWED_KEYS = {"activation", "tasks", "paths", "description"}
_ACTIVATIONS = {"task", "explicit-only", "task-or-explicit", "path", "path-or-explicit"}
_SECTION_TYPES = {
    "### Enabled rules": "rules",
    "### Enabled profiles": "profiles",
    "### Enabled areas": "areas",
}


def validate_glob(pattern: str) -> str:
    if (
        not pattern
        or "\\" in pattern
        or pattern.startswith("/")
        or re.match(r"^[A-Za-z]:", pattern)
        or any(token in pattern for token in "[]{}")
    ):
        raise ValueError(f"invalid Protocol 0.7 path glob {pattern!r}")
    parts = pattern.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"invalid Protocol 0.7 path glob {pattern!r}")
    if any("***" in part or ("**" in part and part != "**") for part in parts):
        raise ValueError(f"invalid Protocol 0.7 path glob {pattern!r}")
    return pattern


def _glob_regex(pattern: str) -> re.Pattern[str]:
    validate_glob(pattern)
    parts = pattern.split("/")
    expression = "^"
    for index, part in enumerate(parts):
        if part == "**":
            if index == len(parts) - 1:
                expression += ".*"
            else:
                expression += "(?:[^/]+/)*"
            continue
        for char in part:
            if char == "*":
                expression += "[^/]*"
            elif char == "?":
                expression += "[^/]"
            else:
                expression += re.escape(char)
        if index < len(parts) - 1:
            expression += "/"
    return re.compile(expression + "$")


def glob_matches(pattern: str, path: str) -> bool:
    return bool(_glob_regex(pattern).fullmatch(path))


def normalize_input_path(project_root: Path, value: str) -> NormalizedPath:
    """Normalize a supplied touched path without requiring it to exist."""

    root = project_root.resolve()
    raw = value.replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f"invalid project-relative path: {value!r}")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"invalid project-relative path: {value!r}")
    normalized = PurePosixPath(*parts).as_posix()
    candidate = root.joinpath(*parts)
    nearest = candidate
    while not nearest.exists() and nearest != root:
        nearest = nearest.parent
    try:
        nearest.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError(f"project path escapes through a symlink: {value!r}") from exc
    if candidate.exists():
        try:
            candidate.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(f"project path escapes through a symlink: {value!r}") from exc
    return NormalizedPath(normalized, not candidate.exists())


def _metadata_values(raw: dict[str, str], module_id: str) -> tuple[str, tuple[str, ...], tuple[str, ...], str]:
    activation = raw.get("activation", "")
    if activation not in _ACTIVATIONS:
        raise ValueError(f"{module_id}: invalid activation {activation!r}")
    tasks: tuple[str, ...] = ()
    if "tasks" in raw:
        tokens = tuple(token.strip() for token in raw["tasks"].split(","))
        if not tokens or any(not token or token not in CANONICAL_TASKS for token in tokens):
            raise ValueError(f"{module_id}: tasks must be comma-separated canonical task tokens")
        tasks = tuple(dict.fromkeys(tokens))
    paths: tuple[str, ...] = ()
    if "paths" in raw:
        value = raw["paths"]
        spans = tuple(_CODE_SPAN_RE.findall(value))
        remainder = _CODE_SPAN_RE.sub("", value).replace(",", "").strip()
        if not spans or remainder:
            raise ValueError(f"{module_id}: paths must be comma-separated Markdown code spans")
        paths = tuple(dict.fromkeys(validate_glob(item) for item in spans))
    description = raw.get("description", "")
    return activation, tasks, paths, description


def _validate_declaration(declaration: ModuleDeclaration) -> None:
    activation = declaration.activation
    kind = declaration.module_type
    if kind == "rules":
        if activation not in {"task", "task-or-explicit", "explicit-only"}:
            raise ValueError(f"{declaration.module_id}: rules do not support {activation!r}")
        if "task" in activation and not declaration.tasks:
            raise ValueError(f"{declaration.module_id}: task activation requires tasks metadata")
        if declaration.paths:
            raise ValueError(f"{declaration.module_id}: rules forbid paths metadata")
    elif kind == "profiles":
        if activation != "explicit-only":
            raise ValueError(f"{declaration.module_id}: profiles must use explicit-only activation")
        if declaration.tasks or declaration.paths:
            raise ValueError(f"{declaration.module_id}: profiles forbid tasks and paths metadata")
    elif kind == "areas":
        if activation not in {"path", "path-or-explicit", "explicit-only"}:
            raise ValueError(f"{declaration.module_id}: areas do not support {activation!r}")
        if "path" in activation and not declaration.paths:
            raise ValueError(f"{declaration.module_id}: path activation requires paths metadata")
        if declaration.tasks:
            raise ValueError(f"{declaration.module_id}: areas forbid tasks metadata")


def parse_optional_module_index(manifest: str, *, legacy_compatible: bool = False) -> tuple[ModuleDeclaration, ...]:
    """Parse the normative nested-bullet optional module grammar.

    Protocol 0.6 one-line declarations can be preserved as explicit-only
    declarations during migration/read compatibility.  They never acquire an
    inferred automatic route.
    """

    lines = manifest.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Optional module index")
    except StopIteration:
        return ()
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    declarations: list[ModuleDeclaration] = []
    seen: set[str] = set()
    current_type: str | None = None
    current_path: str | None = None
    current_meta: dict[str, str] = {}
    legacy_description = ""

    def flush() -> None:
        nonlocal current_path, current_meta, legacy_description
        if current_path is None or current_type is None:
            return
        module_id = normalize_module_identity(current_path)
        expected_prefix = current_type + "/"
        if not module_id.startswith(expected_prefix) or "/" in module_id[len(expected_prefix):]:
            raise ValueError(f"{module_id}: module path does not match {current_type}/")
        if module_id in seen:
            raise ValueError(f"duplicate optional module declaration: {module_id}")
        if not current_meta and legacy_compatible:
            declaration = ModuleDeclaration(
                module_id, current_type, "explicit-only", description=legacy_description
            )
        else:
            activation, tasks, paths, description = _metadata_values(current_meta, module_id)
            declaration = ModuleDeclaration(module_id, current_type, activation, tasks, paths, description)
        _validate_declaration(declaration)
        declarations.append(declaration)
        seen.add(module_id)
        current_path = None
        current_meta = {}
        legacy_description = ""

    for line in lines[start + 1:end]:
        stripped = line.strip()
        if line.startswith("### "):
            flush()
            current_type = _SECTION_TYPES.get(stripped)
            if current_type is None:
                raise ValueError(f"unknown optional module subsection: {stripped}")
            continue
        if not stripped or stripped == "- None enabled." or current_type is None:
            continue
        module_match = _MODULE_LINE_RE.fullmatch(line)
        if module_match:
            flush()
            current_path = module_match.group(1)
            legacy_description = (module_match.group(2) or "").strip()
            if legacy_description and not legacy_compatible:
                raise ValueError(f"{current_path}: Protocol 0.7 module line may not contain inline metadata")
            continue
        meta_match = _META_LINE_RE.fullmatch(line)
        if meta_match and current_path is not None:
            key, value = meta_match.groups()
            if key not in _ALLOWED_KEYS:
                raise ValueError(f"{current_path}: unknown optional module key {key!r}")
            if key in current_meta:
                raise ValueError(f"{current_path}: duplicate optional module key {key!r}")
            current_meta[key] = value.strip()
            continue
        if stripped.startswith("- ") or line.startswith("  - "):
            raise ValueError(f"malformed optional module declaration: {line!r}")
        if current_path is not None:
            raise ValueError(f"{current_path}: continuation lines are not allowed")
    flush()
    return tuple(sorted(declarations, key=lambda item: item.module_id))


def render_optional_declaration(declaration: ModuleDeclaration) -> str:
    lines = [f"- `{declaration.module_id}`", f"  - activation: {declaration.activation}"]
    if declaration.tasks:
        lines.append(f"  - tasks: {', '.join(declaration.tasks)}")
    if declaration.paths:
        lines.append("  - paths: " + ", ".join(f"`{item}`" for item in declaration.paths))
    if declaration.description:
        lines.append(f"  - description: {declaration.description}")
    return "\n".join(lines)
