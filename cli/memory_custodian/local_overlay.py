"""Repo-external Protocol 0.7 local overlay and explicit root binding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import stat

from .entries import (
    generate_entry_id,
    heading_entry_ids,
    LIFECYCLE_FIELDS,
    parse_structured_entries,
    render_active_entry,
    structured_entry_schema_issues,
    validate_evidence,
)
from .locking import (
    ensure_private_directory,
    existing_private_state_directory,
    private_state_directory,
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
    directory: Path | None
    project_id: str
    modules: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    corrupt: bool = False


def _project_state(project_id: str) -> Path:
    projects = private_state_directory("projects")
    return ensure_private_directory(projects / project_id)


def _project_state_path(project_id: str) -> Path:
    path = existing_private_state_directory("projects") / project_id
    if path.exists() or path.is_symlink():
        _validate_local_directory(path)
    return path


def overlay_directory(project_id: str) -> Path:
    project_state = _project_state_path(project_id)
    directory = project_state / "local"
    if directory.exists() or directory.is_symlink():
        _validate_local_directory(directory)
        try:
            directory.resolve().relative_to(project_state.resolve())
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(
                "Local overlay directory escapes its project state directory."
            ) from exc
    return directory


def _binding_path(project_id: str) -> Path:
    return _project_state_path(project_id) / "bindings.json"


def _normalized_root(project_root: Path) -> str:
    return str(project_root.resolve())


def _validate_local_directory(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"Local private state path is not a real directory: {path}")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ValueError(f"Local private state directory is not owned by the current user: {path}")
    if os.name != "nt" and stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError(f"Local private state directory must use mode 0700: {path}")


def read_local_private_file(path: Path) -> str:
    """Read a 0600 owner file through a no-follow descriptor."""

    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"Local private state file is not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"Local private state file is not a regular file: {path}")
        if hasattr(os, "getuid") and opened.st_uid != os.getuid():
            raise ValueError(f"Local private state file is not owned by the current user: {path}")
        if os.name != "nt" and stat.S_IMODE(opened.st_mode) != 0o600:
            raise ValueError(f"Local private state file must use mode 0600: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_bindings(project_id: str) -> tuple[str, ...]:
    path = _binding_path(project_id)
    if not path.exists() and not path.is_symlink():
        return ()
    try:
        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            payload: dict[str, object] = {}
            for key, value in pairs:
                if key in payload:
                    raise ValueError(f"duplicate JSON key: {key}")
                payload[key] = value
            return payload

        payload = json.loads(
            read_local_private_file(path),
            object_pairs_hook=unique_object,
        )
        if not isinstance(payload, dict) or payload.get("project_id") != project_id:
            raise ValueError
        roots = payload["roots"]
        if (
            not isinstance(roots, list)
            or not roots
            or any(not isinstance(item, str) for item in roots)
            or len(roots) != len(set(roots))
        ):
            raise ValueError
        for root in roots:
            path = Path(root)
            if not path.is_absolute() or _normalized_root(path) != root:
                raise ValueError
    except (OSError, RuntimeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Local overlay binding file is corrupt.") from exc
    return tuple(sorted(dict.fromkeys(roots)))


def link_root(
    project_root: Path,
    project_id: str,
    *,
    shared_ids: set[str] | None = None,
) -> tuple[str, ...]:
    directory = overlay_directory(project_id)
    modules = _parse_manifest(directory / "manifest.md", project_id)
    issues = _local_module_issues(modules, directory, project_root)
    issues.extend(_cross_storage_id_issues(modules, shared_ids))
    if issues:
        raise ValueError("Local overlay content is invalid: " + "; ".join(issues))
    roots = set(_read_bindings(project_id))
    current = _normalized_root(project_root)
    if current not in roots and len(roots) == 1:
        previous = next(iter(roots))
        if not Path(previous).is_dir():
            roots = {current}
        else:
            roots.add(current)
    else:
        roots.add(current)
    ordered = tuple(sorted(roots))
    write_private_file(
        _binding_path(project_id),
        json.dumps({"project_id": project_id, "roots": list(ordered)}, sort_keys=True, indent=2) + "\n",
    )
    return _read_bindings(project_id)


def _manifest_text(project_id: str) -> str:
    return (
        "# Local Memory Overlay\n\n"
        f"- local_overlay_schema_version: {LOCAL_SCHEMA_VERSION}\n"
        f"- project_id: {project_id}\n\n"
        "## Preferences\n"
        "- preferences.md\n\n"
        "## Profiles\n"
    )


def enable_overlay(
    project_root: Path,
    project_id: str,
    *,
    shared_ids: set[str] | None = None,
) -> Path:
    project_state = _project_state(project_id)
    _read_bindings(project_id)
    directory = project_state / "local"
    if directory.exists() or directory.is_symlink():
        _validate_local_directory(directory)
        modules = _parse_manifest(directory / "manifest.md", project_id)
        issues = _local_module_issues(modules, directory, project_root)
        issues.extend(_cross_storage_id_issues(modules, shared_ids))
        if issues:
            raise ValueError("Local overlay content is invalid: " + "; ".join(issues))
        return directory
    directory = ensure_private_directory(directory)
    ensure_private_directory(directory / "profiles")
    manifest = directory / "manifest.md"
    preferences = directory / "preferences.md"
    if not manifest.exists():
        write_private_file(manifest, _manifest_text(project_id))
    if not preferences.exists():
        write_private_file(preferences, "# Local Preferences\n\nEntries are newest first.\n")
    modules = _parse_manifest(manifest, project_id)
    issues = _local_module_issues(modules, directory, project_root)
    issues.extend(_cross_storage_id_issues(modules, shared_ids))
    if issues:
        raise ValueError("Local overlay content is invalid: " + "; ".join(issues))
    return directory


def _parse_manifest(path: Path, expected_project_id: str) -> tuple[Path, ...]:
    text = read_local_private_file(path)
    schemas = re.findall(r"(?m)^- local_overlay_schema_version:\s*(\S+)\s*$", text)
    projects = re.findall(r"(?m)^- project_id:\s*(\S+)\s*$", text)
    if len(schemas) != 1 or schemas[0] != LOCAL_SCHEMA_VERSION:
        raise ValueError("Local overlay manifest has an invalid schema version.")
    if len(projects) != 1 or projects[0] != expected_project_id:
        raise ValueError("Local overlay project_id does not match the shared manifest.")
    allowed_lines = {
        "# Local Memory Overlay",
        "## Preferences",
        "## Profiles",
    }
    module_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if line in allowed_lines:
            continue
        if re.fullmatch(r"- (?:local_overlay_schema_version|project_id):\s*\S+\s*", line):
            continue
        module = re.fullmatch(
            r"- ((?:preferences\.md)|(?:profiles/[A-Za-z0-9][A-Za-z0-9._-]*\.md))",
            line,
        )
        if module:
            module_lines.append(module.group(1))
            continue
        raise ValueError(f"Local overlay manifest contains an invalid declaration: {line!r}")
    if len(module_lines) != len(set(module_lines)):
        raise ValueError("Local overlay manifest contains a duplicate module declaration.")
    if "preferences.md" not in module_lines:
        raise ValueError("Local overlay manifest must declare preferences.md exactly once.")
    profiles = path.parent / "profiles"
    if not profiles.exists() and not profiles.is_symlink():
        raise ValueError("Local overlay is missing its required profiles directory.")
    _validate_local_directory(profiles)
    modules: list[Path] = []
    for raw in module_lines:
        candidate = path.parent / raw
        try:
            candidate.resolve().relative_to(path.parent.resolve())
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Local overlay module path escapes its project state directory.") from exc
        if not candidate.exists() and not candidate.is_symlink():
            raise ValueError(f"Local overlay is missing declared module: {raw}")
        read_local_private_file(candidate)
        modules.append(candidate)
    return tuple(modules)


def _local_module_issues(
    modules: tuple[Path, ...],
    directory: Path,
    project_root: Path,
) -> list[str]:
    """Reuse formal Entry validation with local-only storage and scope rules."""

    issues: list[str] = []
    identifiers: dict[str, list[str]] = {}
    for path in modules:
        relative = path.relative_to(directory).as_posix()
        text = read_local_private_file(path)
        entries = parse_structured_entries(path, text)
        for value in heading_entry_ids(text):
            identifiers.setdefault(value.casefold(), []).append(relative)
        for entry in entries:
            issues.extend(structured_entry_schema_issues(entry, relative))
            code = entry.entry_id.split("-", 2)[1].upper()
            if relative == "preferences.md" and code != "PREF":
                issues.append(
                    f"{relative}: {entry.entry_id} type does not match local preference storage"
                )
            if relative.startswith("profiles/") and code != "AREA":
                issues.append(
                    f"{relative}: {entry.entry_id} type does not match local profile storage"
                )
            if entry.scope not in {"local-user", "local-machine"}:
                issues.append(
                    f"{relative}: {entry.entry_id} must use Scope: local-user or local-machine"
                )
            if entry.status != "active":
                issues.append(
                    f"{relative}: {entry.entry_id} has unsupported local Status {entry.status!r}"
                )
            forbidden_relations = sorted(
                field
                for field in (*LIFECYCLE_FIELDS, "Exception-To")
                if entry.field_counts.get(field, 0)
            )
            if forbidden_relations:
                issues.append(
                    f"{relative}: {entry.entry_id} local entries forbid governance relations: "
                    + ", ".join(forbidden_relations)
                )
            if not entry.evidence:
                issues.append(f"{relative}: {entry.entry_id} has no Evidence")
            else:
                try:
                    validate_evidence(
                        entry.evidence,
                        project_root,
                        allow_missing=True,
                    )
                except ValueError:
                    issues.append(
                        f"{relative}: {entry.entry_id} has invalid Evidence schema or unsafe source path"
                    )
    for entry_id, locations in identifiers.items():
        if len(locations) > 1:
            issues.append(
                f"duplicate local Entry ID {entry_id.upper()} in: {', '.join(locations)}"
            )
    return issues


def _cross_storage_id_issues(
    modules: tuple[Path, ...],
    shared_ids: set[str] | None,
) -> list[str]:
    normalized_shared = {value.casefold() for value in (shared_ids or set())}
    return [
        f"duplicate Entry ID across shared/local storage: {entry_id}"
        for path in modules
        for entry_id in heading_entry_ids(read_local_private_file(path))
        if entry_id.casefold() in normalized_shared
    ]


def inspect_overlay(
    project_root: Path,
    project_id: str,
    *,
    disabled: bool = False,
    shared_ids: set[str] | None = None,
) -> LocalOverlay:
    if disabled or not project_id:
        return LocalOverlay(LocalStatus.DISABLED, Path("."), project_id)
    try:
        directory = overlay_directory(project_id)
    except OSError as exc:
        return LocalOverlay(
            LocalStatus.REVIEW,
            None,
            project_id,
            warnings=(f"Unsafe local overlay project directory: {exc}",),
            corrupt=True,
        )
    except ValueError as exc:
        return LocalOverlay(
            LocalStatus.REVIEW,
            None,
            project_id,
            warnings=(f"Unsafe local overlay project directory: {exc}",),
            corrupt=True,
        )
    if not directory.exists():
        binding = directory.parent / "bindings.json"
        if not binding.exists() and not binding.is_symlink():
            return LocalOverlay(LocalStatus.DISABLED, directory, project_id)
        try:
            _read_bindings(project_id)
            warning = "Local overlay binding exists but the required local directory is missing."
        except ValueError as exc:
            warning = str(exc)
        return LocalOverlay(
            LocalStatus.REVIEW,
            directory,
            project_id,
            warnings=(warning,),
            corrupt=True,
        )
    manifest = directory / "manifest.md"
    try:
        roots = _read_bindings(project_id)
    except ValueError as exc:
        return LocalOverlay(
            LocalStatus.REVIEW,
            directory,
            project_id,
            warnings=(str(exc),),
            corrupt=True,
        )
    current = _normalized_root(project_root)
    if current not in roots:
        return LocalOverlay(
            LocalStatus.UNBOUND, directory, project_id,
            warnings=("Existing local overlay is not bound to this normalized project root; run `memory-custodian local link`.",),
        )
    try:
        modules = _parse_manifest(manifest, project_id)
    except (OSError, ValueError) as exc:
        return LocalOverlay(
            LocalStatus.REVIEW,
            directory,
            project_id,
            warnings=(str(exc),),
            corrupt=True,
        )
    entry_issues = _local_module_issues(modules, directory, project_root)
    entry_issues.extend(_cross_storage_id_issues(modules, shared_ids))
    if entry_issues:
        return LocalOverlay(
            LocalStatus.REVIEW,
            directory,
            project_id,
            modules,
            tuple(entry_issues),
            corrupt=True,
        )
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


def add_local_preference(
    project_root: Path,
    project_id: str,
    message: str,
    evidence: tuple[str, ...],
    *,
    shared_ids: set[str] | None = None,
) -> str:
    overlay = inspect_overlay(project_root, project_id, shared_ids=shared_ids)
    if overlay.status == LocalStatus.REVIEW:
        detail = "; ".join(overlay.warnings) or "manual review is required"
        raise ValueError(f"Local overlay requires review before writes: {detail}")
    if overlay.status != LocalStatus.BOUND or overlay.directory is None:
        raise ValueError("Local overlay must be enabled and explicitly linked before adding content.")
    path = overlay.directory / "preferences.md"
    if path not in overlay.modules:
        raise ValueError("Local overlay preferences are not declared by a valid local manifest.")
    existing = read_local_private_file(path)
    findings = scan_text(path, message)
    if any(item.category == "security" for item in findings):
        raise ValueError("Local memory may not store credential-like secrets.")
    existing_ids = set(re.findall(r"MC-PREF-\d{8}-[0-9a-f]{8}", existing, re.I))
    existing_ids.update(shared_ids or ())
    entry_id = generate_entry_id("preference", existing_ids)
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
