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


def _salt() -> bytes:
    root = private_state_directory("transactions")
    path = root / ".binding-salt"
    if not path.exists():
        create_private_file(path, secrets.token_hex(32) + "\n")
    raw = read_private_file(path).strip()
    try:
        value = bytes.fromhex(raw)
    except ValueError as exc:
        raise TransactionError("Private transaction binding salt is malformed.") from exc
    if len(value) != 32:
        raise TransactionError("Private transaction binding salt is malformed.")
    return value


def bootstrap_binding_id(project_root: Path, memory_root: Path) -> str:
    normalized = "\0".join(
        (os.path.normcase(str(project_root.resolve())), os.path.normcase(str(memory_root.absolute())))
    ).encode("utf-8")
    return hmac.new(_salt(), normalized, hashlib.sha256).hexdigest()


def binding_directory(project_root: Path, memory_root: Path, project_id: str | None) -> Path:
    root = private_state_directory("transactions")
    if project_id:
        return ensure_private_directory(root / "project-id" / project_id)
    return ensure_private_directory(root / "bootstrap" / bootstrap_binding_id(project_root, memory_root))


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


def _same_filesystem_replace(path: Path, data: bytes, mode: int) -> None:
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


def unfinished_transaction_directories(binding: Path) -> tuple[Path, ...]:
    if not binding.exists():
        return ()
    found: list[Path] = []
    for directory in sorted(binding.iterdir(), key=lambda item: item.name):
        if not directory.is_dir() or directory.is_symlink():
            continue
        journal_path = directory / "journal.json"
        if not journal_path.exists():
            if any(directory.iterdir()):
                found.append(directory)
            continue
        try:
            journal = json.loads(read_private_file(journal_path))
            phase = journal.get("phase") if isinstance(journal, dict) else None
        except (OSError, json.JSONDecodeError):
            found.append(directory)
            continue
        if phase != "committed" and phase != "rolled-back":
            found.append(directory)
        elif any((directory / "targets").glob("*")) if (directory / "targets").exists() else False:
            found.append(directory)
    return tuple(found)


def ensure_no_unfinished(binding: Path) -> None:
    unfinished = unfinished_transaction_directories(binding)
    if unfinished:
        ids = ", ".join(path.name for path in unfinished)
        raise RecoveryRequiredError(
            f"Unfinished transaction state requires recovery before mutation: {ids}"
        )


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

    binding = binding_directory(project_root, memory_root, project_id)
    ensure_no_unfinished(binding)

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
            exists, _data, _mode = _read_regular_bytes(item.path)
            if exists:
                item.path.unlink()
                _fsync_directory(item.path.parent)
            return (item.path,)
        data = item.text.encode("utf-8")
        if isinstance(item, TextMutation) and not data.endswith(b"\n"):
            data += b"\n"
        exists, _base, mode = _read_regular_bytes(item.path)
        is_private = bool(private_mutations or migration_mutations)
        _same_filesystem_replace(item.path, data, int(mode, 8) if exists and mode else (0o600 if is_private else 0o644))
        return (item.path,)

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
        if path.exists():
            if not path.is_dir() or path.is_symlink():
                raise TransactionError("Planned parent directory became unsafe.")
        else:
            path.mkdir(mode=_mode_value(directory_record.get("mode")), exist_ok=False)
            _fsync_directory(path.parent)
        directory_record["created"] = True
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
            if not _matches(path, bool(target["base_exists"]), target.get("base_sha256"), target.get("base_mode")):
                raise TransactionError(f"Transaction target changed before commit: {target['target_id']}")
            if target["operation"] == "delete":
                path.unlink()
                _fsync_directory(path.parent)
            else:
                prepared = _read_private_bytes(directory / str(target["prepared_path"]))
                if _sha256(prepared) != target["output_sha256"]:
                    raise TransactionError(f"Prepared transaction output is invalid: {target['target_id']}")
                _same_filesystem_replace(path, prepared, _mode_value(target.get("output_mode")))
            target["replaced"] = True
            if ordinal == 0:
                _failpoint("after-first-replace")
            _failpoint(f"after-each-replace:{ordinal + 1}")
            _atomic_journal(journal_path, journal)
        _failpoint("before-committed")
        for target in targets:
            path = _target_path(roots, target)
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
    path = directory / "journal.json"
    if not path.exists():
        raise RecoveryRequiredError("Orphan transaction state lacks a journal.")
    try:
        journal = json.loads(read_private_file(path))
    except json.JSONDecodeError as exc:
        raise RecoveryRequiredError("Transaction journal is malformed.") from exc
    if not isinstance(journal, dict):
        raise RecoveryRequiredError("Transaction journal is malformed.")
    if journal.get("transaction_schema_version") != TRANSACTION_SCHEMA_VERSION:
        raise RecoveryRequiredError("Transaction journal schema is unsupported.")
    if journal.get("transaction_id") != directory.name or not isinstance(journal.get("targets"), list):
        raise RecoveryRequiredError("Transaction journal identity is malformed.")
    return journal


def analyze_transaction(directory: Path, roots: dict[str, RootBinding]) -> RecoveryRecord:
    try:
        journal = load_journal(directory)
    except RecoveryRequiredError as exc:
        return RecoveryRecord(directory.name, "invalid", "unknown", directory, False, False, (str(exc),))
    issues: list[str] = []
    safe_complete = True
    safe_rollback = True
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
        is_base = _matches(path, bool(raw.get("base_exists")), raw.get("base_sha256"), raw.get("base_mode"))
        is_output = _matches(path, bool(raw.get("output_exists")), raw.get("output_sha256"), raw.get("output_mode"))
        prepared_value = raw.get("prepared_path")
        prepared_ok = raw.get("operation") == "delete"
        if prepared_value:
            prepared = directory / str(prepared_value)
            prepared_ok = prepared.exists() and _sha256(_read_private_bytes(prepared)) == raw.get("output_sha256")
        backup_value = raw.get("backup_path")
        backup_ok = not raw.get("base_exists")
        if backup_value:
            backup = directory / str(backup_value)
            backup_ok = backup.exists() and _sha256(_read_private_bytes(backup)) == raw.get("base_sha256")
        if not ((is_base and prepared_ok) or is_output):
            safe_complete = False
            issues.append(f"Target {raw.get('target_id')} is not safely completable.")
        if not ((is_output and backup_ok) or is_base):
            safe_rollback = False
            issues.append(f"Target {raw.get('target_id')} is not safely rollbackable.")
    return RecoveryRecord(
        str(journal["transaction_id"]), str(journal.get("phase", "invalid")),
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
            if not path.exists():
                path.mkdir(mode=_mode_value(directory_record.get("mode")), exist_ok=False)
                _fsync_directory(path.parent)
            directory_record["created"] = True
        order = sorted(targets, key=lambda target: (
            int(target.get("commit_order", 0)),
            str(target.get("root_kind")), str(target.get("path")),
        ))
        for target in order:
            path = _target_path(roots, target)
            if _matches(path, bool(target.get("output_exists")), target.get("output_sha256"), target.get("output_mode")):
                continue
            if not _matches(path, bool(target.get("base_exists")), target.get("base_sha256"), target.get("base_mode")):
                raise RecoveryRequiredError("Target changed during recovery.")
            if target.get("operation") == "delete":
                path.unlink()
                _fsync_directory(path.parent)
            else:
                prepared = _read_private_bytes(directory / str(target["prepared_path"]))
                _same_filesystem_replace(path, prepared, _mode_value(target.get("output_mode")))
        journal["phase"] = "committed"
    else:
        order = sorted(targets, key=lambda target: (
            -int(target.get("commit_order", 0)),
            str(target.get("root_kind")), str(target.get("path")),
        ))
        for target in order:
            path = _target_path(roots, target)
            if _matches(path, bool(target.get("base_exists")), target.get("base_sha256"), target.get("base_mode")):
                continue
            if not _matches(path, bool(target.get("output_exists")), target.get("output_sha256"), target.get("output_mode")):
                raise RecoveryRequiredError("Target changed during recovery.")
            if target.get("base_exists"):
                backup = _read_private_bytes(directory / str(target["backup_path"]))
                _same_filesystem_replace(path, backup, _mode_value(target.get("base_mode")))
            else:
                _validate_write_target(path)
                path.unlink()
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
                if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                    path.rmdir()
                    _fsync_directory(path.parent)
            except FileNotFoundError:
                pass
        journal["phase"] = "rolled-back"
    _atomic_journal(directory / "journal.json", journal)
    _cleanup_transaction(directory, keep_record=False)
    return RecoveryRecord(record.transaction_id, str(journal["phase"]), record.command, directory, True, True, ())
