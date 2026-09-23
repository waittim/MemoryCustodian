"""Crash-recoverable multi-file mutation transactions.

The filesystem remains the source of truth.  The private journal records only
opaque operation metadata, raw-byte digests, modes, and protected locators
needed to complete or roll back an interrupted write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import uuid

from .locking import (
    create_private_file,
    ensure_private_directory,
    existing_private_state_directory,
    private_state_directory,
    read_private_file,
    validate_private_file,
    write_private_file,
)
from .mutations import PrivateDeleteMutation, PrivateTextMutation, TextMutation, _validate_write_target


TRANSACTION_SCHEMA_VERSION = 1
UNFINISHED_PHASES = frozenset({"planned", "prepared", "committing", "recovering", "failed"})
FAILPOINT_ENV = "MEMORY_CUSTODIAN_FAILPOINT"


class TransactionError(OSError):
    """Base error for journaled mutation failures."""


class RecoveryRequiredError(TransactionError):
    """A new mutation was refused because private recovery state exists."""


class TransactionFailpoint(TransactionError):
    """Deterministic test-only crash boundary."""


@dataclass(frozen=True)
class RootBinding:
    kind: str
    root: Path
    public_prefix: str


@dataclass(frozen=True)
class RecoveryRecord:
    transaction_id: str
    phase: str
    command: str
    directory: Path
    safe_complete: bool
    safe_rollback: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class TransactionInventory:
    """Redacted classification of one private transaction-state entry."""

    directory: Path
    kind: str
    transaction_id: str | None
    phase: str | None
    detail: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        os.close(descriptor)


def _read_regular_bytes(path: Path) -> tuple[bool, bytes, str | None]:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return False, b"", None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Transaction target is not a regular non-symlink file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"Transaction target changed during safe open: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return True, b"".join(chunks), f"{stat.S_IMODE(opened.st_mode):04o}"
    finally:
        os.close(descriptor)


def _write_private_bytes(path: Path, data: bytes) -> None:
    ensure_private_directory(path.parent)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def _read_private_bytes(path: Path) -> bytes:
    validate_private_file(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _binding_salt(root: Path, *, create: bool) -> bytes | None:
    path = root / ".binding-salt"
    if create:
        create_private_file(path, secrets.token_hex(32) + "\n")
    else:
        try:
            path.lstat()
        except FileNotFoundError:
            return None
    raw = read_private_file(path).strip()
    try:
        value = bytes.fromhex(raw)
    except ValueError as exc:
        raise TransactionError("Private transaction binding salt is malformed.") from exc
    if len(value) != 32:
        raise TransactionError("Private transaction binding salt is malformed.")
    return value


def _bootstrap_binding_id(project_root: Path, memory_root: Path, salt: bytes) -> str:
    normalized = "\0".join(
        (os.path.normcase(str(project_root.resolve())), os.path.normcase(str(memory_root.absolute())))
    ).encode("utf-8")
    return hmac.new(salt, normalized, hashlib.sha256).hexdigest()


def bootstrap_binding_id(project_root: Path, memory_root: Path) -> str:
    root = private_state_directory("transactions")
    salt = _binding_salt(root, create=True)
    assert salt is not None
    return _bootstrap_binding_id(project_root, memory_root, salt)


def binding_directory(project_root: Path, memory_root: Path, project_id: str | None) -> Path:
    root = private_state_directory("transactions")
    if project_id:
        return ensure_private_directory(root / "project-id" / project_id)
    salt = _binding_salt(root, create=True)
    assert salt is not None
    return ensure_private_directory(
        root / "bootstrap" / _bootstrap_binding_id(project_root, memory_root, salt)
    )


def _existing_private_directory(path: Path) -> Path | None:
    """Validate and return one existing private directory without creating it."""

    try:
        path.lstat()
    except FileNotFoundError:
        return None
    return ensure_private_directory(path)


def existing_binding_directories(
    project_root: Path,
    memory_root: Path,
    project_ids: tuple[str, ...] = (),
) -> tuple[Path, ...]:
    """Return existing transaction bindings relevant to one project.

    Bootstrap state is root/memory-path scoped, while permanent state is
    selected only by the supplied project identities.  The lookup never
    creates a binding, salt, or transaction-state root.
    """

    root = existing_private_state_directory("transactions")
    if _existing_private_directory(root) is None:
        return ()

    bindings: list[Path] = []
    bootstrap_root = _existing_private_directory(root / "bootstrap")
    if bootstrap_root is not None:
        salt = _binding_salt(root, create=False)
        if salt is not None:
            bootstrap = _existing_private_directory(
                bootstrap_root / _bootstrap_binding_id(project_root, memory_root, salt)
            )
            if bootstrap is not None:
                bindings.append(bootstrap)

    project_id_root = _existing_private_directory(root / "project-id")
    if project_id_root is not None:
        for project_id in dict.fromkeys(item for item in project_ids if item):
            binding = _existing_private_directory(project_id_root / project_id)
            if binding is not None:
                bindings.append(binding)
    return tuple(dict.fromkeys(bindings))


def _atomic_journal(path: Path, journal: dict[str, object]) -> None:
    payload = json.dumps(journal, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    write_private_file(path, payload)
    _fsync_directory(path.parent)


def _failpoint(name: str) -> None:
    selected = os.environ.get(FAILPOINT_ENV, "")
    if selected == name or (name.startswith("after-each-replace:") and selected == "after-each-replace"):
        raise TransactionFailpoint(f"Transaction interrupted at failpoint {name}.")


def _target_state(path: Path) -> tuple[bool, str | None, str | None]:
    exists, data, mode = _read_regular_bytes(path)
    return exists, _sha256(data) if exists else None, mode


def _matches(path: Path, exists: bool, digest: str | None, mode: str | None) -> bool:
    try:
        observed_exists, observed_digest, observed_mode = _target_state(path)
    except (OSError, ValueError):
        return False
    return (
        observed_exists == exists
        and (not exists or observed_digest == digest)
        and (not exists or mode is None or observed_mode == mode)
    )


def _same_filesystem_replace(
    path: Path,
    data: bytes,
    mode: int,
    *,
    trusted_root: Path | None = None,
) -> None:
    if trusted_root is not None:
        _validate_target_for_root(trusted_root, path)
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".txn", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.chmod(temporary, mode)
        if trusted_root is not None:
            _validate_target_for_root(trusted_root, path)
        else:
            _validate_write_target(path)
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _trusted_root_contains(root: Path, path: Path) -> bool:
    """Check lexical and existing-realpath containment beneath ``root``."""

    try:
        root_absolute = root.expanduser().absolute()
        candidate = path.expanduser().absolute()
        candidate.relative_to(root_absolute)
        root_real = root_absolute.resolve(strict=False)
        parent_real = candidate.parent.resolve(strict=False)
        parent_real.relative_to(root_real)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _validate_target_for_root(root: Path, path: Path) -> None:
    """Revalidate a target and every ancestor immediately before mutation."""

    if not _trusted_root_contains(root, path):
        raise TransactionError("Transaction target is outside its trusted root.")
    try:
        _validate_write_target(path)
    except (OSError, ValueError) as exc:
        raise TransactionError("Transaction target has an unsafe ancestor.") from exc


def _validate_directory_for_root(root: Path, path: Path) -> None:
    """Revalidate a planned directory and its ancestors without creating it."""

    if not _trusted_root_contains(root, path):
        raise TransactionError("Planned directory is outside its trusted root.")
    try:
        # Validate the directory itself as an ancestor of a non-existent
        # probe target; unlike _validate_write_target(path), this accepts a
        # real directory as the target under inspection.
        _validate_write_target(path / ".memory-custodian-directory-check")
    except (OSError, ValueError) as exc:
        raise TransactionError("Planned directory has an unsafe ancestor.") from exc


def _unlink_in_trusted_parent(root: Path, path: Path) -> None:
    """Unlink through a verified parent directory handle when supported."""

    _validate_target_for_root(root, path)
    parent = path.parent
    directory_fd: int | None = None
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if os.name != "nt":
            try:
                directory_fd = os.open(parent, directory_flags)
                os.unlink(path.name, dir_fd=directory_fd)
            except TypeError:
                # A platform may expose open() but not unlink(dir_fd=...).
                path.unlink()
            except OSError as exc:
                raise TransactionError("Transaction target parent became unsafe.") from exc
        else:
            # Windows and platforms without unlink(dir_fd=...) still receive
            # the immediate ancestor/scope revalidation above.
            path.unlink()
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _directory_identity(path: Path) -> dict[str, int]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise TransactionError("Planned directory is not a real directory.")
    return {"st_dev": int(metadata.st_dev), "st_ino": int(metadata.st_ino)}


def _directory_identity_matches(path: Path, identity: object) -> bool:
    if not isinstance(identity, dict):
        return False
    if not all(key in identity for key in ("st_dev", "st_ino")):
        return False
    try:
        observed = _directory_identity(path)
        expected = {
            "st_dev": int(identity["st_dev"]),
            "st_ino": int(identity["st_ino"]),
        }
    except (OSError, TransactionError, TypeError, ValueError, KeyError):
        return False
    return observed == expected


def _safe_private_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")):
        return False
    parts = value.replace("\\", "/").split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _private_artifact_matches(
    path: Path,
    expected_digest: object,
) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
        return _sha256(_read_private_bytes(path)) == expected_digest
    except (OSError, ValueError):
        return False


def _safe_relative(root: Path, path: Path) -> str:
    absolute = path.absolute()
    try:
        relative = absolute.relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError("Transaction target escapes its trusted root.") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Transaction target has an invalid relative locator.")
    return relative.as_posix()


def _target_path(roots: dict[str, RootBinding], target: dict[str, object]) -> Path:
    root_kind = str(target.get("root_kind", ""))
    binding = roots.get(root_kind)
    if binding is None:
        raise ValueError(f"Transaction root is unavailable: {root_kind}")
    relative = str(target.get("path", ""))
    candidate = binding.root / relative
    if _safe_relative(binding.root, candidate) != relative.replace("\\", "/"):
        raise ValueError("Transaction target locator is invalid.")
    return candidate


def _mode_value(value: object, default: int = 0o644) -> int:
    if value is None:
        return default
    if not isinstance(value, str) or not value or any(ch not in "01234567" for ch in value):
        raise ValueError("Transaction mode is invalid.")
    return int(value, 8)


def _classify_journal(
    directory: Path,
    journal: object,
) -> tuple[str, str, str | None, str | None]:
    if not isinstance(journal, dict):
        return "malformed", "journal is not an object", None, None
    transaction_id = journal.get("transaction_id")
    phase = journal.get("phase")
    if journal.get("transaction_schema_version") != TRANSACTION_SCHEMA_VERSION:
        return "unsupported", "journal schema is unsupported", (
            str(transaction_id) if transaction_id is not None else None
        ), str(phase) if phase is not None else None
    if transaction_id != directory.name or not isinstance(journal.get("targets"), list):
        return "malformed", "journal identity or targets are malformed", (
            str(transaction_id) if transaction_id is not None else None
        ), str(phase) if phase is not None else None
    if not isinstance(phase, str) or phase not in UNFINISHED_PHASES | {"committed", "rolled-back"}:
        return "malformed", "journal phase is invalid", directory.name, str(phase)
    allowed_roots = {"shared", "local-overlay", "migration-state"}
    allowed_operations = {"create", "replace", "delete"}
    for target in journal["targets"]:
        if not isinstance(target, dict):
            return "malformed", "journal target is not an object", directory.name, str(phase)
        if not isinstance(target.get("root_kind"), str) or target.get("root_kind") not in allowed_roots:
            return "malformed", "journal target root is invalid", directory.name, str(phase)
        if not _safe_private_relative(target.get("path")):
            return "unsafe", "journal target locator is unsafe", directory.name, str(phase)
        if not isinstance(target.get("operation"), str) or target.get("operation") not in allowed_operations:
            return "malformed", "journal target operation is invalid", directory.name, str(phase)
        for locator_key in ("backup_path", "prepared_path"):
            locator = target.get(locator_key)
            if locator is not None and not _safe_private_relative(locator):
                return "unsafe", "journal artifact locator is unsafe", directory.name, str(phase)
    directories = journal.get("created_directories", [])
    if not isinstance(directories, list):
        return "malformed", "created directory inventory is malformed", directory.name, str(phase)
    for item in directories:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("root_kind"), str)
            or item.get("root_kind") not in allowed_roots
        ):
            return "malformed", "created directory inventory is malformed", directory.name, str(phase)
        if not _safe_private_relative(item.get("path")):
            return "unsafe", "created directory locator is unsafe", directory.name, str(phase)
        if not isinstance(item.get("created"), bool):
            return "malformed", "created directory progress is malformed", directory.name, str(phase)
        if item.get("created") and not isinstance(item.get("identity"), dict):
            return "unsafe", "created directory identity is missing", directory.name, str(phase)

    targets_directory = directory / "targets"
    if targets_directory.is_symlink():
        return "unsafe", "transaction target state is symlinked", directory.name, str(phase)
    try:
        unexpected = [
            child for child in directory.iterdir()
            if child.name not in {"journal.json", "targets"}
        ]
    except OSError:
        return "unsafe", "transaction state directory cannot be inspected", directory.name, str(phase)
    if unexpected:
        return "orphan", "unexpected transaction state artifact remains", directory.name, str(phase)
    if targets_directory.exists() and not targets_directory.is_dir():
        return "unsafe", "transaction target state is not a directory", directory.name, str(phase)
    try:
        target_children = tuple(targets_directory.iterdir()) if targets_directory.exists() else ()
    except OSError:
        return "unsafe", "transaction target state cannot be inspected", directory.name, str(phase)
    if any(child.is_symlink() or not child.is_file() for child in target_children):
        return "unsafe", "transaction target artifact is unsafe", directory.name, str(phase)
    has_artifacts = bool(target_children)
    if phase in {"committed", "rolled-back"}:
        if has_artifacts:
            return "committed-cleanup" if phase == "committed" else "orphan", (
                "committed cleanup is pending" if phase == "committed" else "rolled-back artifacts remain"
            ), directory.name, str(phase)
        return "clean", "", directory.name, str(phase)
    return "unfinished", "recovery is required", directory.name, str(phase)


def transaction_inventory(binding: Path) -> tuple[TransactionInventory, ...]:
    if not binding.exists():
        return ()
    found: list[TransactionInventory] = []
    for directory in sorted(binding.iterdir(), key=lambda item: item.name):
        if directory.is_symlink():
            found.append(TransactionInventory(directory, "symlink", directory.name, None, "transaction entry is symlinked"))
            continue
        if not directory.is_dir():
            found.append(TransactionInventory(directory, "orphan", None, None, "transaction entry is not a directory"))
            continue
        journal_path = directory / "journal.json"
        if journal_path.is_symlink():
            found.append(TransactionInventory(directory, "unsafe", directory.name, None, "journal is symlinked"))
            continue
        if not journal_path.exists():
            found.append(TransactionInventory(directory, "orphan", directory.name, None, "transaction journal is missing"))
            continue
        try:
            journal = json.loads(read_private_file(journal_path))
        except json.JSONDecodeError:
            found.append(TransactionInventory(directory, "malformed", directory.name, None, "transaction journal is malformed"))
            continue
        except OSError:
            found.append(TransactionInventory(directory, "unsafe", directory.name, None, "transaction journal is unsafe"))
            continue
        kind, detail, transaction_id, phase = _classify_journal(directory, journal)
        found.append(TransactionInventory(directory, kind, transaction_id, phase, detail))
    return tuple(item for item in found if item.kind != "clean")


def unfinished_transaction_directories(binding: Path) -> tuple[Path, ...]:
    return tuple(item.directory for item in transaction_inventory(binding))


def ensure_no_unfinished(binding: Path) -> None:
    unfinished = unfinished_transaction_directories(binding)
    if unfinished:
        ids = ", ".join(path.name for path in unfinished)
        raise RecoveryRequiredError(
            f"Unfinished transaction state requires recovery before mutation: {ids}"
        )


def ensure_no_unfinished_for_project(
    project_root: Path,
    memory_root: Path,
    project_ids: tuple[str, ...] = (),
) -> None:
    """Reject recovery state in this project's bootstrap/permanent bindings."""

    unfinished = tuple(
        directory
        for binding in existing_binding_directories(
            project_root, memory_root, project_ids
        )
        for directory in unfinished_transaction_directories(binding)
    )
    if unfinished:
        ids = ", ".join(path.name for path in unfinished)
        raise RecoveryRequiredError(
            f"Unfinished transaction state requires recovery before mutation: {ids}"
        )


def _manifest_project_id(text: str) -> str | None:
    """Best-effort identity discovery for transaction binding handoffs."""

    from .protocol import project_id_from_manifest

    try:
        return project_id_from_manifest(text, required=False)
    except ValueError:
        # The command-specific preflight remains authoritative for malformed
        # legacy/repair input. An invalid value cannot name a safe binding.
        return None


def _related_project_ids(
    memory_root: Path,
    project_id: str | None,
    shared_mutations: tuple[TextMutation, ...],
) -> tuple[str, ...]:
    """Collect current, target, and selected transaction project identities."""

    values: list[str] = []
    if project_id:
        values.append(project_id)
    manifest_path = memory_root / "manifest.md"
    exists, current, _mode = _read_regular_bytes(manifest_path)
    if exists:
        try:
            current_id = _manifest_project_id(current.decode("utf-8"))
        except UnicodeDecodeError:
            current_id = None
        if current_id:
            values.append(current_id)
    manifest_absolute = manifest_path.absolute()
    for mutation in shared_mutations:
        if mutation.path.absolute() != manifest_absolute:
            continue
        target_id = _manifest_project_id(mutation.text)
        if target_id:
            values.append(target_id)
    return tuple(dict.fromkeys(values))


def apply_transaction(
    *,
    project_root: Path,
    memory_root: Path,
    project_id: str | None,
    command: str,
    plan_id: str,
    shared_mutations: tuple[TextMutation, ...] = (),
    private_mutations: tuple[PrivateTextMutation, ...] = (),
    private_deletions: tuple[PrivateDeleteMutation, ...] = (),
    private_directories: tuple[Path, ...] = (),
    local_root: Path | None = None,
    migration_mutations: tuple[PrivateTextMutation, ...] = (),
    migration_deletions: tuple[PrivateDeleteMutation, ...] = (),
    migration_root: Path | None = None,
    erasure_scope: dict[str, object] | None = None,
    force_journal: bool = False,
) -> tuple[Path, ...]:
    """Apply one prevalidated mutation set, journaling every multi-target write."""

    if (
        not shared_mutations and not private_mutations and not private_deletions
        and not private_directories and not migration_mutations and not migration_deletions
    ):
        return ()
    paths = (
        [item.path for item in shared_mutations]
        + [item.path for item in private_mutations]
        + [item.path for item in private_deletions]
        + [item.path for item in migration_mutations]
        + [item.path for item in migration_deletions]
    )
    if len(paths) != len(set(paths)):
        raise ValueError("Transaction contains the same target more than once.")
    for path in paths:
        _validate_write_target(path)

    roots = {"shared": RootBinding("shared", project_root.absolute(), "shared")}
    if private_mutations or private_deletions:
        if local_root is None:
            private_items = (*private_mutations, *private_deletions)
            common = Path(os.path.commonpath([str(item.path.parent) for item in private_items]))
            local_root = common
        roots["local-overlay"] = RootBinding("local-overlay", local_root.absolute(), "local")
    elif private_directories:
        if local_root is None:
            raise ValueError("Private transaction directories require a trusted local root.")
        roots["local-overlay"] = RootBinding("local-overlay", local_root.absolute(), "local")

    if migration_mutations or migration_deletions:
        if migration_root is None:
            raise ValueError("Migration-state mutations require a trusted private root.")
        roots["migration-state"] = RootBinding(
            "migration-state", migration_root.absolute(), "migration-state"
        )

    for directory_path in private_directories:
        _safe_relative(roots["local-overlay"].root, directory_path)
        if directory_path.exists() and (not directory_path.is_dir() or directory_path.is_symlink()):
            raise ValueError("Transaction directory target is not a real directory.")

    for item in shared_mutations:
        _safe_relative(roots["shared"].root, item.path)
    for item in (*private_mutations, *private_deletions):
        _safe_relative(roots["local-overlay"].root, item.path)
    for item in (*migration_mutations, *migration_deletions):
        _safe_relative(roots["migration-state"].root, item.path)

    ensure_no_unfinished_for_project(
        project_root,
        memory_root,
        _related_project_ids(memory_root, project_id, shared_mutations),
    )

    # A true single-file replacement retains the established atomic writer.
    if len(paths) == 1 and not force_journal:
        item = (
            shared_mutations[0] if shared_mutations
            else private_mutations[0] if private_mutations
            else private_deletions[0] if private_deletions
            else migration_mutations[0] if migration_mutations
            else migration_deletions[0]
        )
        if isinstance(item, PrivateDeleteMutation):
            if private_deletions:
                trusted_root = roots["local-overlay"].root
            elif migration_deletions:
                trusted_root = roots["migration-state"].root
            else:
                trusted_root = roots["shared"].root
            _validate_target_for_root(trusted_root, item.path)
            exists, _data, _mode = _read_regular_bytes(item.path)
            if exists:
                _unlink_in_trusted_parent(trusted_root, item.path)
                _fsync_directory(item.path.parent)
            return (item.path,)
        data = item.text.encode("utf-8")
        if isinstance(item, TextMutation) and not data.endswith(b"\n"):
            data += b"\n"
        exists, _base, mode = _read_regular_bytes(item.path)
        is_private = bool(private_mutations or migration_mutations)
        if private_mutations:
            trusted_root = roots["local-overlay"].root
        elif migration_mutations:
            trusted_root = roots["migration-state"].root
        else:
            trusted_root = roots["shared"].root
        _same_filesystem_replace(
            item.path,
            data,
            int(mode, 8) if exists and mode else (0o600 if is_private else 0o644),
            trusted_root=trusted_root,
        )
        return (item.path,)

    binding = binding_directory(project_root, memory_root, project_id)
    transaction_id = uuid.uuid4().hex
    directory = ensure_private_directory(binding / transaction_id)
    target_directory = ensure_private_directory(directory / "targets")
    journal_path = directory / "journal.json"
    targets: list[dict[str, object]] = []
    payloads: list[bytes] = []
    ordered_items: list[tuple[str, TextMutation | PrivateTextMutation]] = [
        *(('shared', item) for item in shared_mutations),
        *(('local-overlay', item) for item in private_mutations),
        *(('local-overlay', item) for item in private_deletions),
        *(('migration-state', item) for item in migration_mutations),
        *(('migration-state', item) for item in migration_deletions),
    ]
    for index, (root_kind, item) in enumerate(ordered_items, start=1):
        binding_root = roots[root_kind].root
        exists, before, base_mode = _read_regular_bytes(item.path)
        deleting = isinstance(item, PrivateDeleteMutation)
        output = b"" if deleting else item.text.encode("utf-8")
        if isinstance(item, TextMutation) and not output.endswith(b"\n"):
            output += b"\n"
        output_mode = base_mode or ("0600" if root_kind != "shared" else "0644")
        target_id = f"{index:04d}"
        targets.append({
            "target_id": target_id,
            "root_kind": root_kind,
            "path": _safe_relative(binding_root, item.path),
            "operation": "delete" if deleting else "replace" if exists else "create",
            "commit_group": "authority" if item.path.name in {"manifest.md", "bindings.json"} else "content",
            "commit_order": (
                2 if item.path.name == "bindings.json"
                else 1 if item.path.name == "manifest.md"
                else 0
            ),
            "base_exists": exists,
            "base_sha256": _sha256(before) if exists else None,
            "mode_semantics": "windows-basic" if os.name == "nt" else "posix",
            "base_mode": base_mode,
            "output_exists": not deleting,
            "output_sha256": None if deleting else _sha256(output),
            "output_mode": None if deleting else output_mode,
            "backup_path": f"targets/{target_id}.backup" if exists else None,
            "prepared_path": None if deleting else f"targets/{target_id}.prepared",
            "replaced": False,
        })
        payloads.append(output)

    created_directories: list[dict[str, object]] = []
    seen_directories: set[tuple[str, str]] = set()
    for root_kind, item in ordered_items:
        root = roots[root_kind].root
        cursor = item.path.parent
        missing: list[Path] = []
        while cursor != root and not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for directory_path in reversed(missing):
            relative = _safe_relative(root, directory_path)
            key = (root_kind, relative)
            if key in seen_directories:
                continue
            seen_directories.add(key)
            created_directories.append({
                "root_kind": root_kind,
                "path": relative,
                "mode": "0700" if root_kind != "shared" else "0755",
                "base_exists": False,
                "created": False,
                "identity": None,
            })
    for directory_path in private_directories:
        root = roots["local-overlay"].root
        cursor = directory_path
        missing: list[Path] = []
        while cursor != root and not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for planned in reversed(missing):
            relative = _safe_relative(root, planned)
            key = ("local-overlay", relative)
            if key in seen_directories:
                continue
            seen_directories.add(key)
            created_directories.append({
                "root_kind": "local-overlay",
                "path": relative,
                "mode": "0700",
                "base_exists": False,
                "created": False,
                "identity": None,
            })

    journal: dict[str, object] = {
        "transaction_schema_version": TRANSACTION_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "project_binding": {
            "kind": "project-id" if project_id else "bootstrap",
            "id": project_id or bootstrap_binding_id(project_root, memory_root),
        },
        "command": command,
        "plan_id": plan_id,
        "phase": "planned",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "targets": targets,
        "created_directories": sorted(
            created_directories,
            key=lambda item: (str(item["root_kind"]), str(item["path"])),
        ),
    }
    if erasure_scope is not None:
        journal["erasure_scope"] = dict(erasure_scope)
    _atomic_journal(journal_path, journal)
    _failpoint("after-planned-before-first-artifact")

    for index, target in enumerate(targets):
        path = _target_path(roots, target)
        exists, before, _mode = _read_regular_bytes(path)
        if exists:
            _write_private_bytes(directory / str(target["backup_path"]), before)
        if index == 0:
            _failpoint("after-first-backup")
        if target["prepared_path"] is not None:
            _write_private_bytes(directory / str(target["prepared_path"]), payloads[index])
    journal["phase"] = "prepared"
    _atomic_journal(journal_path, journal)
    _failpoint("after-journal-prepared")
    journal["phase"] = "committing"
    _atomic_journal(journal_path, journal)

    for directory_record in journal["created_directories"]:
        root = roots[str(directory_record["root_kind"])].root
        path = root / str(directory_record["path"])
        _validate_directory_for_root(root, path)
        if path.exists():
            if not path.is_dir() or path.is_symlink():
                raise TransactionError("Planned parent directory became unsafe.")
            # The directory appeared after planning.  It was not created by
            # this transaction and must never be removed on rollback.
            directory_record["created"] = False
            directory_record["identity"] = None
        else:
            path.mkdir(mode=_mode_value(directory_record.get("mode")), exist_ok=False)
            _fsync_directory(path.parent)
            directory_record["created"] = True
            directory_record["identity"] = _directory_identity(path)
        _atomic_journal(journal_path, journal)

    order = sorted(range(len(targets)), key=lambda index: (
        int(targets[index].get("commit_order", 0)),
        str(targets[index]["root_kind"]),
        str(targets[index]["path"]),
    ))
    try:
        for ordinal, index in enumerate(order):
            target = targets[index]
            path = _target_path(roots, target)
            _validate_target_for_root(roots[str(target["root_kind"])].root, path)
            if not _matches(path, bool(target["base_exists"]), target.get("base_sha256"), target.get("base_mode")):
                raise TransactionError(f"Transaction target changed before commit: {target['target_id']}")
            if target["operation"] == "delete":
                _unlink_in_trusted_parent(roots[str(target["root_kind"])].root, path)
                _fsync_directory(path.parent)
            else:
                prepared = _read_private_bytes(directory / str(target["prepared_path"]))
                if _sha256(prepared) != target["output_sha256"]:
                    raise TransactionError(f"Prepared transaction output is invalid: {target['target_id']}")
                _same_filesystem_replace(
                    path,
                    prepared,
                    _mode_value(target.get("output_mode")),
                    trusted_root=roots[str(target["root_kind"])].root,
                )
            target["replaced"] = True
            if ordinal == 0:
                _failpoint("after-first-replace")
            _failpoint(f"after-each-replace:{ordinal + 1}")
            _atomic_journal(journal_path, journal)
        _failpoint("before-committed")
        for target in targets:
            path = _target_path(roots, target)
            _validate_target_for_root(roots[str(target["root_kind"])].root, path)
            if not _matches(path, bool(target["output_exists"]), target.get("output_sha256"), target.get("output_mode")):
                raise TransactionError(f"Committed transaction output failed verification: {target['target_id']}")
        journal["phase"] = "committed"
        _atomic_journal(journal_path, journal)
        _failpoint("after-committed-before-cleanup")
    except Exception:
        # Once every target has been verified and the committed marker is
        # durable, a cleanup interruption is not a failed commit.  Preserve
        # that phase so recovery can perform idempotent completion/cleanup.
        if journal.get("phase") != "committed":
            journal["phase"] = "failed"
            try:
                _atomic_journal(journal_path, journal)
            except OSError:
                pass
        raise

    _cleanup_transaction(directory, keep_record=False)
    return tuple(paths[index] for index in order)


def apply_plan_transaction(
    plan,
    memory_root: Path,
    *,
    local_root: Path | None = None,
    erasure_scope: dict[str, object] | None = None,
    force_journal: bool = False,
) -> tuple[Path, ...]:
    """Apply a ``MutationPlan`` without serializing its private form publicly."""

    if plan.project_root is None:
        raise ValueError("A transactional mutation plan requires project_root.")
    try:
        parsed = uuid.UUID(str(plan.project_id))
        project_id = str(parsed) if parsed.version == 4 else None
    except (ValueError, TypeError, AttributeError):
        project_id = None
    if plan.command.startswith("init") or not (memory_root / "manifest.md").exists():
        project_id = None
    return apply_transaction(
        project_root=plan.project_root,
        memory_root=memory_root,
        project_id=project_id,
        command=plan.command,
        plan_id=plan.plan_id,
        shared_mutations=tuple(plan.mutations),
        private_mutations=tuple(plan.private_mutations),
        local_root=local_root,
        erasure_scope=erasure_scope,
        force_journal=force_journal,
    )


def _cleanup_transaction(directory: Path, *, keep_record: bool) -> None:
    targets = directory / "targets"
    if targets.exists() and targets.is_dir() and not targets.is_symlink():
        for child in sorted(targets.iterdir()):
            validate_private_file(child)
            child.unlink()
        targets.rmdir()
    if keep_record:
        return
    journal = directory / "journal.json"
    if journal.exists():
        validate_private_file(journal)
        journal.unlink()
    try:
        directory.rmdir()
    except OSError:
        pass


def load_journal(directory: Path) -> dict[str, object]:
    if directory.is_symlink() or not directory.is_dir():
        raise RecoveryRequiredError("Transaction state directory is unsafe.")
    path = directory / "journal.json"
    if path.is_symlink():
        raise RecoveryRequiredError("Transaction journal is unsafe.")
    if not path.exists():
        raise RecoveryRequiredError("Orphan transaction state lacks a journal.")
    try:
        journal = json.loads(read_private_file(path))
    except json.JSONDecodeError as exc:
        raise RecoveryRequiredError("Transaction journal is malformed.") from exc
    except OSError as exc:
        raise RecoveryRequiredError("Transaction journal is unsafe.") from exc
    if not isinstance(journal, dict):
        raise RecoveryRequiredError("Transaction journal is malformed.")
    if journal.get("transaction_schema_version") != TRANSACTION_SCHEMA_VERSION:
        raise RecoveryRequiredError("Transaction journal schema is unsupported.")
    if journal.get("transaction_id") != directory.name or not isinstance(journal.get("targets"), list):
        raise RecoveryRequiredError("Transaction journal identity is malformed.")
    kind, detail, _transaction_id, _phase = _classify_journal(directory, journal)
    if kind in {"malformed", "unsupported", "unsafe", "orphan"}:
        raise RecoveryRequiredError(detail.capitalize() + ".")
    return journal


def analyze_transaction(directory: Path, roots: dict[str, RootBinding]) -> RecoveryRecord:
    try:
        journal = load_journal(directory)
    except RecoveryRequiredError as exc:
        return RecoveryRecord(directory.name, "invalid", "unknown", directory, False, False, (str(exc),))
    issues: list[str] = []
    safe_complete = True
    safe_rollback = True
    phase = str(journal.get("phase", "invalid"))
    for raw in journal["targets"]:
        if not isinstance(raw, dict):
            issues.append("Malformed target record.")
            safe_complete = safe_rollback = False
            continue
        try:
            path = _target_path(roots, raw)
        except ValueError:
            issues.append(f"Target {raw.get('target_id', 'unknown')} cannot be resolved safely.")
            safe_complete = safe_rollback = False
            continue
        try:
            _validate_target_for_root(roots[str(raw.get("root_kind"))].root, path)
        except (KeyError, TransactionError):
            issues.append(f"Target {raw.get('target_id', 'unknown')} has an unsafe ancestor.")
            safe_complete = safe_rollback = False
            continue
        is_base = _matches(path, bool(raw.get("base_exists")), raw.get("base_sha256"), raw.get("base_mode"))
        is_output = _matches(path, bool(raw.get("output_exists")), raw.get("output_sha256"), raw.get("output_mode"))
        prepared_value = raw.get("prepared_path")
        prepared_ok = raw.get("operation") == "delete"
        if prepared_value:
            prepared = directory / str(prepared_value)
            prepared_ok = _private_artifact_matches(prepared, raw.get("output_sha256"))
        backup_value = raw.get("backup_path")
        backup_ok = not raw.get("base_exists")
        if backup_value:
            backup = directory / str(backup_value)
            backup_ok = _private_artifact_matches(backup, raw.get("base_sha256"))
        if not ((is_base and prepared_ok) or is_output):
            safe_complete = False
            issues.append(f"Target {raw.get('target_id')} is not safely completable.")
        if not ((is_output and backup_ok) or is_base):
            safe_rollback = False
            issues.append(f"Target {raw.get('target_id')} is not safely rollbackable.")
    for raw_directory in journal.get("created_directories", []):
        if not isinstance(raw_directory, dict) or not raw_directory.get("created"):
            continue
        try:
            root = roots[str(raw_directory["root_kind"])].root
            path = root / str(raw_directory["path"])
            _safe_relative(root, path)
        except (KeyError, TypeError, ValueError):
            safe_complete = safe_rollback = False
            issues.append("Created directory inventory cannot be resolved safely.")
            continue
        if path.is_symlink() or (path.exists() and not _directory_identity_matches(path, raw_directory.get("identity"))):
            safe_rollback = False
            issues.append("Created directory identity changed during recovery.")
    if phase == "committed":
        safe_rollback = False
        issues.append("Committed transaction can only be completed, not rolled back.")
    return RecoveryRecord(
        str(journal["transaction_id"]), phase,
        str(journal.get("command", "unknown")), directory,
        safe_complete, safe_rollback, tuple(sorted(set(issues))),
    )


def recover_transaction(
    directory: Path,
    roots: dict[str, RootBinding],
    *,
    action: str,
) -> RecoveryRecord:
    if action not in {"complete", "rollback"}:
        raise ValueError("Recovery action must be complete or rollback.")
    record = analyze_transaction(directory, roots)
    if action == "rollback" and record.phase == "committed":
        raise RecoveryRequiredError(
            "Committed transaction cleanup can only be completed, not rolled back."
        )
    allowed = record.safe_complete if action == "complete" else record.safe_rollback
    if not allowed:
        raise RecoveryRequiredError("Automatic recovery is unsafe; manual recovery is required.")
    journal = load_journal(directory)
    journal["phase"] = "recovering"
    _atomic_journal(directory / "journal.json", journal)
    _failpoint("while-recovering")
    targets = list(journal["targets"])
    if action == "complete":
        for directory_record in journal.get("created_directories", []):
            root = roots[str(directory_record["root_kind"])].root
            path = root / str(directory_record["path"])
            _validate_directory_for_root(root, path)
            if not path.exists():
                path.mkdir(mode=_mode_value(directory_record.get("mode")), exist_ok=False)
                _fsync_directory(path.parent)
                directory_record["created"] = True
                directory_record["identity"] = _directory_identity(path)
                _atomic_journal(directory / "journal.json", journal)
            elif path.is_symlink() or not path.is_dir():
                raise RecoveryRequiredError("Planned parent directory became unsafe during recovery.")
            elif directory_record.get("created") and not _directory_identity_matches(
                path, directory_record.get("identity")
            ):
                raise RecoveryRequiredError("Planned parent directory identity changed during recovery.")
        order = sorted(targets, key=lambda target: (
            int(target.get("commit_order", 0)),
            str(target.get("root_kind")), str(target.get("path")),
        ))
        for target in order:
            path = _target_path(roots, target)
            _validate_target_for_root(roots[str(target["root_kind"])].root, path)
            if _matches(path, bool(target.get("output_exists")), target.get("output_sha256"), target.get("output_mode")):
                continue
            if not _matches(path, bool(target.get("base_exists")), target.get("base_sha256"), target.get("base_mode")):
                raise RecoveryRequiredError("Target changed during recovery.")
            if target.get("operation") == "delete":
                _unlink_in_trusted_parent(roots[str(target["root_kind"])].root, path)
                _fsync_directory(path.parent)
            else:
                prepared = _read_private_bytes(directory / str(target["prepared_path"]))
                _same_filesystem_replace(
                    path,
                    prepared,
                    _mode_value(target.get("output_mode")),
                    trusted_root=roots[str(target["root_kind"])].root,
                )
        journal["phase"] = "committed"
    else:
        order = sorted(targets, key=lambda target: (
            -int(target.get("commit_order", 0)),
            str(target.get("root_kind")), str(target.get("path")),
        ))
        for target in order:
            path = _target_path(roots, target)
            _validate_target_for_root(roots[str(target["root_kind"])].root, path)
            if _matches(path, bool(target.get("base_exists")), target.get("base_sha256"), target.get("base_mode")):
                continue
            if not _matches(path, bool(target.get("output_exists")), target.get("output_sha256"), target.get("output_mode")):
                raise RecoveryRequiredError("Target changed during recovery.")
            if target.get("base_exists"):
                backup = _read_private_bytes(directory / str(target["backup_path"]))
                _same_filesystem_replace(
                    path,
                    backup,
                    _mode_value(target.get("base_mode")),
                    trusted_root=roots[str(target["root_kind"])].root,
                )
            else:
                _unlink_in_trusted_parent(roots[str(target["root_kind"])].root, path)
                _fsync_directory(path.parent)
        for directory_record in sorted(
            journal.get("created_directories", []),
            key=lambda item: (str(item.get("root_kind")), str(item.get("path"))),
            reverse=True,
        ):
            if not directory_record.get("created"):
                continue
            root = roots[str(directory_record["root_kind"])].root
            path = root / str(directory_record["path"])
            try:
                _validate_directory_for_root(root, path)
                if path.is_symlink() or (path.exists() and not _directory_identity_matches(path, directory_record.get("identity"))):
                    raise RecoveryRequiredError("Created directory identity changed during recovery.")
                if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                    path.rmdir()
                    _fsync_directory(path.parent)
            except FileNotFoundError:
                pass
        journal["phase"] = "rolled-back"
    _atomic_journal(directory / "journal.json", journal)
    _cleanup_transaction(directory, keep_record=False)
    return RecoveryRecord(record.transaction_id, str(journal["phase"]), record.command, directory, True, True, ())
