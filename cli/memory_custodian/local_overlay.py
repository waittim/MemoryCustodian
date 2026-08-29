"""Repo-external Protocol 0.7 local overlay and explicit root binding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping

from .entries import (
    StructuredEntry,
    entry_unit_issues,
    generate_entry_id,
    heading_entry_ids,
    LIFECYCLE_FIELDS,
    normalize_entry_schema_version,
    parse_structured_entries,
    render_active_entry,
    structured_entry_schema_issues,
    validate_evidence,
)
from .markdown import headings as markdown_headings
from .markdown import visible_lines
from .locking import (
    ensure_private_directory,
    existing_private_state_directory,
    private_state_directory,
    write_private_file,
)
from .protocol import (
    CURRENT_ENTRY_SCHEMA_VERSION,
    CURRENT_PROTOCOL_VERSION,
    ENTRY_SCHEMA_MIGRATION_MESSAGE,
    compare_versions,
    manifest_contract_metadata,
    project_id_from_manifest,
    read_managed_text,
)
from .scanning import scan_text


LOCAL_SCHEMA_VERSION = "1"


class LocalStatus(str, Enum):
    DISABLED = "DISABLED"
    UNBOUND = "UNBOUND"
    BOUND = "BOUND"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class CapturedLocalFile:
    """One local overlay file captured together with its parsed Entries.

    The text and parser output are deliberately kept together.  Consumers of
    an overlay inspection must use this immutable source record instead of
    reopening the private file after validation has completed.
    """

    path: Path
    relative: str
    text: str
    entries: tuple[StructuredEntry, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalOverlaySnapshot:
    """Read-only local overlay view produced by one inspection.

    ``files`` includes the local manifest followed by each declared module.
    Every file is represented by the exact text and parsed Entries observed
    during this inspection.  The tuple boundary prevents downstream callers
    from replacing or reordering captured inputs.
    """

    directory: Path
    files: tuple[CapturedLocalFile, ...] = ()

    @property
    def manifest(self) -> CapturedLocalFile | None:
        return next(
            (item for item in self.files if item.relative == "manifest.md"),
            None,
        )

    @property
    def module_files(self) -> tuple[CapturedLocalFile, ...]:
        return tuple(item for item in self.files if item.relative != "manifest.md")

    @property
    def entries(self) -> tuple[StructuredEntry, ...]:
        return tuple(entry for item in self.module_files for entry in item.entries)


@dataclass(frozen=True)
class LocalOverlay:
    status: LocalStatus
    directory: Path | None
    project_id: str
    modules: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    corrupt: bool = False
    snapshot: LocalOverlaySnapshot | None = None

    @property
    def captured_modules(self) -> tuple[CapturedLocalFile, ...]:
        """Return captured declared modules without reopening private files."""

        return self.snapshot.module_files if self.snapshot is not None else ()


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
        with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as handle:
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


def _accept_overlay_snapshot(
    overlay: LocalOverlay,
    project_id: str,
    operation: str,
    *,
    allow_disabled: bool = False,
) -> LocalOverlay:
    """Accept one inspected overlay for a mutation without reopening it."""

    if overlay.project_id != project_id:
        raise ValueError("Local overlay inspection belongs to a different project_id.")
    if overlay.corrupt:
        detail = "; ".join(overlay.warnings) or "manual review is required"
        raise ValueError("Local overlay content is invalid: " + detail)
    if overlay.snapshot is None:
        if allow_disabled and overlay.status == LocalStatus.DISABLED:
            return overlay
        detail = "; ".join(overlay.warnings) or "manual review is required"
        raise ValueError(f"Local overlay requires review before {operation}: {detail}")
    return overlay


def link_root(
    project_root: Path,
    project_id: str,
    *,
    shared_ids: set[str] | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
    overlay: LocalOverlay | None = None,
) -> tuple[str, ...]:
    if overlay is None:
        overlay = inspect_overlay(
            project_root,
            project_id,
            shared_ids=shared_ids,
            entry_schema_version=entry_schema_version,
            capture_unbound=True,
        )
    overlay = _accept_overlay_snapshot(overlay, project_id, "linking")
    directory = overlay.directory
    if directory is None:
        raise ValueError("Local overlay inspection did not capture a usable directory.")
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


def enable_overlay(
    project_root: Path,
    project_id: str,
    *,
    shared_ids: set[str] | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
    overlay: LocalOverlay | None = None,
) -> LocalOverlay:
    if overlay is None:
        overlay = inspect_overlay(
            project_root,
            project_id,
            shared_ids=shared_ids,
            entry_schema_version=entry_schema_version,
            capture_unbound=True,
        )
    overlay = _accept_overlay_snapshot(
        overlay,
        project_id,
        "enabling",
        allow_disabled=True,
    )
    project_state = _project_state(project_id)
    _read_bindings(project_id)
    directory = project_state / "local"
    if directory.exists() or directory.is_symlink():
        if overlay.snapshot is None:
            detail = "; ".join(overlay.warnings) or "local overlay changed after inspection"
            raise ValueError("Local overlay requires review before enabling: " + detail)
        _validate_local_directory(directory)
        return overlay
    directory = ensure_private_directory(directory)
    ensure_private_directory(directory / "profiles")
    manifest = directory / "manifest.md"
    preferences = directory / "preferences.md"
    if not manifest.exists():
        write_private_file(manifest, _manifest_text(project_id))
    if not preferences.exists():
        write_private_file(preferences, "# Local Preferences\n\nEntries are newest first.\n")
    created = inspect_overlay(
        project_root,
        project_id,
        shared_ids=shared_ids,
        entry_schema_version=entry_schema_version,
        capture_unbound=True,
    )
    return _accept_overlay_snapshot(created, project_id, "enabling")


def _parse_manifest(
    path: Path,
    expected_project_id: str,
    *,
    text: str | None = None,
    captured_text: dict[Path, str] | None = None,
) -> tuple[Path, ...]:
    """Validate local manifest topology from supplied/captured text.

    ``captured_text`` is used by ``inspect_overlay`` to retain the one read of
    each declared module.  Legacy callers that omit it keep the historical
    disk-backed API.
    """

    if text is None:
        text = read_local_private_file(path)
    # A local manifest is a small Markdown document, not an unordered bag of
    # allowed lines.  Count only real (non-fenced, non-indented) headings so a
    # code example cannot satisfy or duplicate the manifest topology.
    visible_lines(text)
    headings = markdown_headings(text)
    expected_headings = (
        (1, "local memory overlay"),
        (2, "preferences"),
        (2, "profiles"),
    )
    if tuple((heading.level, heading.title) for heading in headings) != expected_headings:
        raise ValueError(
            "Local overlay manifest must contain exactly one `# Local Memory Overlay`, "
            "then one `## Preferences` and one `## Profiles` section."
        )
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
    section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if line in allowed_lines:
            if line == "## Preferences":
                section = "preferences"
            elif line == "## Profiles":
                section = "profiles"
            continue
        if re.fullmatch(r"- (?:local_overlay_schema_version|project_id):\s*\S+\s*", line):
            if section is not None:
                raise ValueError(
                    "Local overlay metadata must appear before module sections."
                )
            continue
        module = re.fullmatch(
            r"- ((?:preferences\.md)|(?:profiles/[A-Za-z0-9][A-Za-z0-9._-]*\.md))",
            line,
        )
        if module:
            declared = module.group(1)
            if section is None:
                raise ValueError(
                    f"Local overlay module declaration is outside a section: {line!r}"
                )
            if section == "preferences" and declared != "preferences.md":
                raise ValueError(
                    f"Profile module declaration must be under `## Profiles`: {line!r}"
                )
            if section == "profiles" and declared == "preferences.md":
                raise ValueError(
                    f"Preferences module declaration must be under `## Preferences`: {line!r}"
                )
            module_lines.append(declared)
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
        module_text = read_local_private_file(candidate)
        if captured_text is not None:
            captured_text[candidate] = module_text
        modules.append(candidate)
    return tuple(modules)


def _local_entry_issues(
    relative: str,
    entries: tuple[StructuredEntry, ...],
    project_root: Path,
) -> list[str]:
    """Validate already-parsed local Entries without touching the filesystem."""

    issues: list[str] = []
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
    return issues


def _capture_local_file(
    path: Path,
    directory: Path,
    project_root: Path,
    *,
    text: str | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> CapturedLocalFile:
    """Capture one local module and all diagnostics from that captured text."""

    relative = path.relative_to(directory).as_posix()
    if text is None:
        try:
            text = read_local_private_file(path)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return CapturedLocalFile(
                path,
                relative,
                "",
                diagnostics=(f"{relative}: Markdown entry parsing failed: {exc}",),
            )

    diagnostics: list[str] = []
    try:
        diagnostics.extend(entry_unit_issues(text, relative))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        diagnostics.append(f"{relative}: Markdown entry parsing failed: {exc}")
        return CapturedLocalFile(path, relative, text, diagnostics=tuple(diagnostics))
    try:
        entries = tuple(parse_structured_entries(
            path,
            text,
            entry_schema_version=entry_schema_version,
        ))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        diagnostics.append(f"{relative}: Markdown entry parsing failed: {exc}")
        return CapturedLocalFile(path, relative, text, diagnostics=tuple(diagnostics))
    diagnostics.extend(_local_entry_issues(relative, entries, project_root))
    return CapturedLocalFile(
        path,
        relative,
        text,
        entries,
        tuple(dict.fromkeys(diagnostics)),
    )


def _captured_modules(
    modules: tuple[Path, ...],
    directory: Path,
    project_root: Path,
    *,
    captured_text: Mapping[Path, str] | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> tuple[CapturedLocalFile, ...]:
    return tuple(
        _capture_local_file(
            path,
            directory,
            project_root,
            text=(captured_text[path] if captured_text is not None and path in captured_text else None),
            entry_schema_version=entry_schema_version,
        )
        for path in modules
    )


def _local_module_issues(
    modules: tuple[Path, ...],
    directory: Path,
    project_root: Path,
    *,
    captured_files: Mapping[Path, CapturedLocalFile] | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> list[str]:
    """Validate local modules, reusing captured text and parsed Entries."""

    files = tuple(
        captured_files[path]
        if captured_files is not None and path in captured_files
        else _capture_local_file(
            path,
            directory,
            project_root,
            entry_schema_version=entry_schema_version,
        )
        for path in modules
    )
    issues = [diagnostic for item in files for diagnostic in item.diagnostics]
    identifiers: dict[str, list[str]] = {}
    for item in files:
        for entry in item.entries:
            identifiers.setdefault(entry.entry_id.casefold(), []).append(item.relative)
    for entry_id, locations in identifiers.items():
        if len(locations) > 1:
            issues.append(
                f"duplicate local Entry ID {entry_id.upper()} in: {', '.join(locations)}"
            )
    return list(dict.fromkeys(issues))


def _cross_storage_id_issues(
    modules: tuple[Path, ...],
    shared_ids: set[str] | None,
    *,
    captured_files: Mapping[Path, CapturedLocalFile] | None = None,
) -> list[str]:
    normalized_shared = {value.casefold() for value in (shared_ids or set())}
    issues: list[str] = []
    for path in modules:
        if captured_files is not None and path in captured_files:
            values = tuple(entry.entry_id for entry in captured_files[path].entries)
        else:
            try:
                values = heading_entry_ids(read_local_private_file(path))
            except (OSError, RuntimeError, TypeError, ValueError):
                # The module parser already reports malformed Markdown.  Do not
                # turn that diagnostic into an uncaught exception while checking
                # the cross-storage ID index.
                continue
        issues.extend(
            f"duplicate Entry ID across shared/local storage: {entry_id}"
            for entry_id in values
            if entry_id.casefold() in normalized_shared
        )
    return issues


def inspect_overlay(
    project_root: Path,
    project_id: str,
    *,
    disabled: bool = False,
    shared_ids: set[str] | None = None,
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
    capture_unbound: bool = False,
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
    if current not in roots and not capture_unbound:
        return LocalOverlay(
            LocalStatus.UNBOUND, directory, project_id,
            warnings=("Existing local overlay is not bound to this normalized project root; run `memory-custodian local link`.",),
        )
    try:
        # Capture the manifest and every declared module once.  The returned
        # snapshot is the only local input a downstream read is allowed to
        # consume; it must not reopen these paths after validation.
        manifest_text = read_local_private_file(manifest)
        module_texts: dict[Path, str] = {}
        modules = _parse_manifest(
            manifest,
            project_id,
            text=manifest_text,
            captured_text=module_texts,
        )
    except (OSError, ValueError) as exc:
        return LocalOverlay(
            LocalStatus.REVIEW,
            directory,
            project_id,
            warnings=(str(exc),),
            corrupt=True,
        )
    module_files = _captured_modules(
        modules,
        directory,
        project_root,
        captured_text=module_texts,
        entry_schema_version=entry_schema_version,
    )
    captured_by_path = {item.path: item for item in module_files}
    entry_issues = _local_module_issues(
        modules,
        directory,
        project_root,
        captured_files=captured_by_path,
        entry_schema_version=entry_schema_version,
    )
    cross_storage_issues = _cross_storage_id_issues(
        modules,
        shared_ids,
        captured_files=captured_by_path,
    )
    entry_issues.extend(cross_storage_issues)
    local_snapshot = LocalOverlaySnapshot(
        directory,
        (
            CapturedLocalFile(manifest, "manifest.md", manifest_text),
            *module_files,
        ),
    )
    if entry_issues:
        return LocalOverlay(
            LocalStatus.REVIEW,
            directory,
            project_id,
            modules,
            tuple(entry_issues),
            corrupt=True,
            snapshot=local_snapshot,
        )
    if current not in roots:
        status = LocalStatus.UNBOUND
        warnings = (
            "Existing local overlay is not bound to this normalized project root; run `memory-custodian local link`.",
        )
    else:
        status = LocalStatus.REVIEW if len(roots) > 1 else LocalStatus.BOUND
        warnings = (
            ("The same project_id is explicitly bound to multiple roots; review cross-repository overlay reuse.",)
            if len(roots) > 1 else ()
        )
    return LocalOverlay(
        status,
        directory,
        project_id,
        modules,
        warnings,
        snapshot=local_snapshot,
    )


def project_identity(memory_dir: Path) -> str:
    return project_id_from_manifest(
        read_managed_text(memory_dir, memory_dir / "manifest.md"), required=False
    ) or ""


def validated_project_identity(
    memory_dir: Path,
    *,
    manifest_text: str | None = None,
    allow_legacy_entry_schema: bool = False,
) -> str:
    """Return the validated shared project id from one captured manifest.

    Existing callers omit ``manifest_text`` and retain the disk-backed API.
    Read paths that already own a MemorySnapshot pass its captured value,
    including an empty value for a missing manifest, so identity validation
    cannot cross the snapshot boundary and observe a later repair.  A
    compatibility reader may explicitly allow distributed schema-1 metadata;
    mutation callers retain the strict default.
    """

    metadata = manifest_contract_metadata(
        read_managed_text(memory_dir, memory_dir / "manifest.md")
        if manifest_text is None
        else manifest_text,
        allow_legacy_entry_schema=allow_legacy_entry_schema,
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
    entry_schema_version: str = CURRENT_ENTRY_SCHEMA_VERSION,
) -> str:
    schema = normalize_entry_schema_version(entry_schema_version)
    if schema != CURRENT_ENTRY_SCHEMA_VERSION:
        raise ValueError(ENTRY_SCHEMA_MIGRATION_MESSAGE)
    overlay = inspect_overlay(
        project_root,
        project_id,
        shared_ids=shared_ids,
        entry_schema_version=schema,
    )
    if overlay.status == LocalStatus.REVIEW:
        detail = "; ".join(overlay.warnings) or "manual review is required"
        raise ValueError(f"Local overlay requires review before writes: {detail}")
    if overlay.status != LocalStatus.BOUND or overlay.directory is None:
        raise ValueError("Local overlay must be enabled and explicitly linked before adding content.")
    path = overlay.directory / "preferences.md"
    if path not in overlay.modules:
        raise ValueError("Local overlay preferences are not declared by a valid local manifest.")
    captured = next(
        (item for item in overlay.captured_modules if item.path == path),
        None,
    )
    if captured is None:
        raise ValueError("Local overlay preferences were not captured by inspection.")
    existing = captured.text
    findings = scan_text(path, message)
    if any(item.category == "security" for item in findings):
        raise ValueError("Local memory may not store credential-like secrets.")
    existing_ids: set[str] = set()
    for module_file in overlay.captured_modules:
        existing_ids.update(entry.entry_id for entry in module_file.entries)
    existing_ids.update(shared_ids or ())
    entry_id = generate_entry_id("preference", existing_ids)
    if entry_id.casefold() in {value.casefold() for value in existing_ids}:
        raise ValueError(f"Entry ID collision in local overlay: {entry_id}")
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
