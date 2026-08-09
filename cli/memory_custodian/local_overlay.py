"""Repo-external Protocol 0.7 local overlay and explicit root binding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re

from .entries import generate_entry_id, render_active_entry
from .locking import (
    ensure_private_directory,
    existing_private_state_directory,
    private_state_directory,
    validate_private_file,
    write_private_file,
)
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    manifest_contract_metadata,
    project_id_from_manifest,
)
from .scanning import scan_text


LOCAL_SCHEMA_VERSION = "1"


class LocalStatus(str, Enum):
    DISABLED = "DISABLED"
    UNBOUND = "UNBOUND"
    BOUND = "BOUND"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class LocalOverlay:
    status: LocalStatus
    directory: Path
    project_id: str
    modules: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()


def _project_state(project_id: str) -> Path:
    projects = private_state_directory("projects")
    return ensure_private_directory(projects / project_id)


def _project_state_path(project_id: str) -> Path:
    path = existing_private_state_directory("projects") / project_id
    if path.exists() or path.is_symlink():
        ensure_private_directory(path)
    return path


def overlay_directory(project_id: str) -> Path:
    return _project_state_path(project_id) / "local"


def _binding_path(project_id: str) -> Path:
    return _project_state_path(project_id) / "bindings.json"


def _normalized_root(project_root: Path) -> str:
    return str(project_root.resolve())


def _read_bindings(project_id: str) -> tuple[str, ...]:
    path = _binding_path(project_id)
    if not path.exists():
        return ()
    validate_private_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        roots = payload["roots"]
        if not isinstance(roots, list) or any(not isinstance(item, str) for item in roots):
            raise ValueError
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Local overlay binding file is corrupt.") from exc
    return tuple(sorted(dict.fromkeys(roots)))


def link_root(project_root: Path, project_id: str) -> tuple[str, ...]:
    roots = set(_read_bindings(project_id))
    roots.add(_normalized_root(project_root))
    ordered = tuple(sorted(roots))
    write_private_file(
        _binding_path(project_id),
        json.dumps({"project_id": project_id, "roots": list(ordered)}, sort_keys=True, indent=2) + "\n",
    )
    return ordered


def _manifest_text(project_id: str) -> str:
    return (
        "# Local Memory Overlay\n\n"
        f"- local_overlay_schema_version: {LOCAL_SCHEMA_VERSION}\n"
        f"- project_id: {project_id}\n\n"
        "## Preferences\n"
        "- preferences.md\n\n"
        "## Profiles\n"
    )


def enable_overlay(project_id: str) -> Path:
    directory = ensure_private_directory(_project_state(project_id) / "local")
    ensure_private_directory(directory / "profiles")
    manifest = directory / "manifest.md"
    preferences = directory / "preferences.md"
    if not manifest.exists():
        write_private_file(manifest, _manifest_text(project_id))
    if not preferences.exists():
        write_private_file(preferences, "# Local Preferences\n\nEntries are newest first.\n")
    return directory


def _parse_manifest(path: Path, expected_project_id: str) -> tuple[Path, ...]:
    validate_private_file(path)
    text = path.read_text(encoding="utf-8")
    schema = re.search(r"(?m)^- local_overlay_schema_version:\s*(\S+)\s*$", text)
    project = re.search(r"(?m)^- project_id:\s*(\S+)\s*$", text)
    if not schema or schema.group(1) != LOCAL_SCHEMA_VERSION:
        raise ValueError("Local overlay manifest has an invalid schema version.")
    if not project or project.group(1) != expected_project_id:
        raise ValueError("Local overlay project_id does not match the shared manifest.")
    allowed_lines = {
        "# Local Memory Overlay",
        "## Preferences",
        "## Profiles",
    }
    module_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped in allowed_lines:
            continue
        if re.fullmatch(r"- (?:local_overlay_schema_version|project_id):\s*\S+", stripped):
            continue
        module = re.fullmatch(
            r"- ((?:preferences\.md)|(?:profiles/[A-Za-z0-9][A-Za-z0-9._-]*\.md))",
            stripped,
        )
        if module:
            module_lines.append(module.group(1))
            continue
        raise ValueError(f"Local overlay manifest contains an invalid declaration: {line!r}")
    if len(module_lines) != len(set(module_lines)):
        raise ValueError("Local overlay manifest contains a duplicate module declaration.")
    modules: list[Path] = []
    for raw in module_lines:
        candidate = path.parent / raw
        try:
            candidate.resolve().relative_to(path.parent.resolve())
        except ValueError as exc:
            raise ValueError("Local overlay module path escapes its project state directory.") from exc
        if candidate.exists():
            validate_private_file(candidate)
            modules.append(candidate)
    return tuple(modules)


def inspect_overlay(project_root: Path, project_id: str, *, disabled: bool = False) -> LocalOverlay:
    if disabled or not project_id:
        return LocalOverlay(LocalStatus.DISABLED, Path("."), project_id)
    try:
        directory = overlay_directory(project_id)
    except OSError as exc:
        return LocalOverlay(
            LocalStatus.REVIEW,
            Path("__invalid_local_overlay_state__"),
            project_id,
            warnings=(f"Unsafe local overlay project directory: {exc}",),
        )
    if not directory.exists():
        return LocalOverlay(LocalStatus.DISABLED, directory, project_id)
    manifest = directory / "manifest.md"
    try:
        roots = _read_bindings(project_id)
    except ValueError as exc:
        return LocalOverlay(LocalStatus.REVIEW, directory, project_id, warnings=(str(exc),))
    current = _normalized_root(project_root)
    if current not in roots:
        return LocalOverlay(
            LocalStatus.UNBOUND, directory, project_id,
            warnings=("Existing local overlay is not bound to this normalized project root; run `memory-custodian local link`.",),
        )
    try:
        modules = _parse_manifest(manifest, project_id)
    except (OSError, ValueError) as exc:
        return LocalOverlay(LocalStatus.REVIEW, directory, project_id, warnings=(str(exc),))
    status = LocalStatus.REVIEW if len(roots) > 1 else LocalStatus.BOUND
    warnings = (
        ("The same project_id is explicitly bound to multiple roots; review cross-repository overlay reuse.",)
        if len(roots) > 1 else ()
    )
    return LocalOverlay(status, directory, project_id, modules, warnings)


def project_identity(memory_dir: Path) -> str:
    return project_id_from_manifest(
        (memory_dir / "manifest.md").read_text(encoding="utf-8"), required=False
    ) or ""


def validated_project_identity(memory_dir: Path) -> str:
    metadata = manifest_contract_metadata(
        (memory_dir / "manifest.md").read_text(encoding="utf-8")
    )
    if compare_versions(
        metadata.get("protocol_version", "0.5"),
        CURRENT_PROTOCOL_VERSION,
    ) != 0:
        raise ValueError("Local overlay access requires Protocol 0.7.")
    return metadata["project_id"]


def add_local_preference(project_root: Path, project_id: str, message: str, evidence: tuple[str, ...]) -> str:
    overlay = inspect_overlay(project_root, project_id)
    if overlay.status not in {LocalStatus.BOUND, LocalStatus.REVIEW}:
        raise ValueError("Local overlay must be enabled and explicitly linked before adding content.")
    path = overlay.directory / "preferences.md"
    existing = path.read_text(encoding="utf-8")
    findings = scan_text(path, message)
    if any(item.category == "security" for item in findings):
        raise ValueError("Local memory may not store credential-like secrets.")
    entry_id = generate_entry_id("preference", set(re.findall(r"MC-PREF-\d{8}-[0-9a-f]{8}", existing, re.I)))
    entry = render_active_entry(
        "preference", entry_id, "Local preference", message, None,
        "local-user", evidence,
    )
    updated = existing.rstrip() + "\n\n" + entry + "\n"
    write_private_file(path, updated)
    return entry_id


def render_overlay_status(overlay: LocalOverlay) -> None:
    print(f"Local overlay status: {overlay.status.value}")
    for warning in overlay.warnings:
        print(f"- {warning}")
