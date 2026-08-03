"""Project-scoped mutation locks stored outside repositories."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import time
import uuid


class LockError(OSError):
    pass


class PrivateStateError(OSError):
    pass


class UnsafePrivateStateError(PrivateStateError):
    pass


MALFORMED_LOCK_RECOVERY_AGE_SECONDS = 300.0


@dataclass(frozen=True)
class ProjectMutationGuard:
    project_id: str | None
    manifest_text: str | None
    bootstrap_lock_path: Path
    project_lock_path: Path | None


def _fallback_state_root() -> Path:
    suffix = str(os.getuid()) if hasattr(os, "getuid") else hashlib.sha256(
        str(Path.home()).encode("utf-8")
    ).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"memory-custodian-state-{suffix}"


def state_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "MemoryCustodian" / "state" if base else _fallback_state_root()
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "memory-custodian"
    try:
        return Path.home() / ".local" / "state" / "memory-custodian"
    except RuntimeError:
        return _fallback_state_root()


def ensure_private_directory(path: Path) -> Path:
    """Create a private state directory and reject symlink/non-directory targets."""

    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise UnsafePrivateStateError(
            f"Private state path is not a real directory: {path}"
        )
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise UnsafePrivateStateError(
            f"Private state directory is not owned by the current user: {path}"
        )
    try:
        path.chmod(0o700)
    except OSError as exc:
        raise PrivateStateError(f"Cannot secure private state directory: {path}") from exc
    return path


def private_state_directory(name: str) -> Path:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"Invalid private state directory name: {name!r}")
    try:
        root = ensure_private_directory(state_root())
        return ensure_private_directory(root / name)
    except UnsafePrivateStateError:
        raise
    except OSError:
        root = ensure_private_directory(_fallback_state_root())
        return ensure_private_directory(root / name)


def existing_private_state_directory(name: str) -> Path:
    """Locate existing private state without creating directories."""

    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"Invalid private state directory name: {name!r}")
    primary = state_root() / name
    fallback = _fallback_state_root() / name
    if primary.exists():
        ensure_private_directory(primary)
        return primary
    if fallback.exists():
        ensure_private_directory(fallback)
        return fallback
    return primary


def _fallback_private_directory(name: str) -> Path:
    root = ensure_private_directory(_fallback_state_root())
    return ensure_private_directory(root / name)


def _private_open_flags(base: int) -> int:
    return base | getattr(os, "O_NOFOLLOW", 0)


def validate_private_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise UnsafePrivateStateError(
            f"Private state file is not a regular file: {path}"
        )
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise UnsafePrivateStateError(
            f"Private state file is not owned by the current user: {path}"
        )
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise PrivateStateError(f"Cannot secure private state file: {path}") from exc


def create_private_file(path: Path, content: str) -> bool:
    """Create a private regular file without following symlinks."""

    ensure_private_directory(path.parent)
    flags = _private_open_flags(os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        validate_private_file(path)
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    validate_private_file(path)
    return True


def write_private_file(path: Path, content: str) -> None:
    """Atomically replace a private state file without following symlinks."""

    ensure_private_directory(path.parent)
    validate_private_file(path)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = _private_open_flags(os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.chmod(temporary, 0o600)
        validate_private_file(path)
        os.replace(temporary, path)
        validate_private_file(path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_private_file(path: Path) -> str:
    validate_private_file(path)
    descriptor = os.open(path, _private_open_flags(os.O_RDONLY))
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        return handle.read()


def discard_private_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        validate_private_file(path)
        path.unlink()
    except FileNotFoundError:
        pass


def discard_expired_private_files(
    directory: Path,
    *,
    max_age_seconds: float,
    suffixes: tuple[str, ...],
) -> tuple[Path, ...]:
    """Remove old private regular files while preserving fresh preview state."""

    if max_age_seconds <= 0:
        raise ValueError("Private state max age must be positive.")
    ensure_private_directory(directory)
    now = time.time()
    removed: list[Path] = []
    for path in sorted(directory.iterdir()):
        if not path.name.endswith(suffixes):
            continue
        validate_private_file(path)
        try:
            age = now - path.lstat().st_mtime
        except FileNotFoundError:
            continue
        if age <= max_age_seconds:
            continue
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
    return tuple(removed)


def lock_path(project_id: str) -> Path:
    return state_root() / "locks" / f"{project_id}.lock"


def bootstrap_lock_id(project_root: Path) -> str:
    """Return a path-stable lock identity for projects without a manifest identity yet."""

    normalized = os.path.normcase(str(project_root.resolve()))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"bootstrap-{digest}"


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def stale_lock(path: Path, minimum_age: float = 60.0) -> bool:
    try:
        raw = read_private_file(path)
        age = time.time() - path.lstat().st_mtime
    except OSError:
        return False
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
        hostname = payload["hostname"]
        pid = payload["pid"]
        if not isinstance(hostname, str) or not hostname:
            raise ValueError
        if isinstance(pid, bool):
            raise ValueError
        pid = int(pid)
        if pid <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return age > max(minimum_age, MALFORMED_LOCK_RECOVERY_AGE_SECONDS)
    return (
        hostname == socket.gethostname()
        and not _pid_exists(pid)
        and age > minimum_age
    )


@contextmanager
def mutation_lock(
    project_id: str,
    project_root: Path,
    command: str,
    *,
    timeout: float = 10.0,
    break_stale: bool = False,
):
    path = lock_path(project_id)
    try:
        path = private_state_directory("locks") / path.name
    except UnsafePrivateStateError:
        raise
    except OSError:
        path = _fallback_private_directory("locks") / f"{project_id}.lock"
    deadline = time.monotonic() + timeout
    payload = {
        "project_id": project_id,
        "project_root": str(project_root),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
    }
    used_fallback = path.is_relative_to(_fallback_state_root())
    while True:
        try:
            descriptor = os.open(
                path,
                _private_open_flags(os.O_CREAT | os.O_EXCL | os.O_WRONLY),
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            break
        except PermissionError:
            if used_fallback:
                raise
            path = _fallback_private_directory("locks") / f"{project_id}.lock"
            used_fallback = True
            continue
        except FileExistsError:
            validate_private_file(path)
            if break_stale and stale_lock(path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise LockError(f"Timed out waiting for mutation lock: {path}")
            time.sleep(0.15)
    try:
        yield path
    finally:
        try:
            current = json.loads(read_private_file(path))
            if current.get("pid") == os.getpid():
                path.unlink()
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            pass


@contextmanager
def project_mutation_guard(
    project_root: Path,
    manifest_path: Path,
    command: str,
    *,
    timeout: float = 10.0,
    break_stale: bool = False,
    project_id_hint: str | None = None,
    create_project_id: bool = False,
    allow_legacy: bool = False,
    allow_metadata_repair: bool = False,
):
    """Serialize every project mutation through one bootstrap-to-project handoff."""

    bootstrap_id = bootstrap_lock_id(project_root)
    with mutation_lock(
        bootstrap_id,
        project_root,
        f"{command} bootstrap",
        timeout=timeout,
        break_stale=break_stale,
    ) as bootstrap_path:
        manifest_text = (
            manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        )
        current_project_id: str | None = None
        if manifest_text is not None:
            from .protocol import (
                CURRENT_PROTOCOL_VERSION,
                compare_versions,
                project_id_from_manifest,
                protocol_contract_metadata,
                strict_protocol_metadata,
            )

            if allow_metadata_repair:
                metadata = strict_protocol_metadata(
                    manifest_text,
                    allow_missing_section=True,
                )
            else:
                metadata = protocol_contract_metadata(
                    manifest_text,
                    allow_missing_section=allow_legacy,
                )
            version = metadata.get("protocol_version")
            if version:
                comparison = compare_versions(version, CURRENT_PROTOCOL_VERSION)
                if comparison is None:
                    raise ValueError(
                        f"Project manifest has invalid protocol version {version!r}."
                    )
                if comparison > 0:
                    raise ValueError(
                        "Project protocol is newer than this CLI supports; "
                        "update MemoryCustodian before mutating memory."
                    )
                if comparison < 0 and not (allow_legacy or allow_metadata_repair):
                    raise ValueError(
                        "Project protocol is older than this writer supports; "
                        "run `memory-custodian migrate`."
                    )
            current_project_id = project_id_from_manifest(manifest_text, required=False)

        project_id = current_project_id or project_id_hint
        if project_id is not None:
            try:
                parsed = uuid.UUID(project_id)
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"Invalid project mutation identity: {project_id!r}") from exc
            if parsed.version != 4 or str(parsed) != project_id.lower():
                raise ValueError(f"Invalid project mutation identity: {project_id!r}")
            project_id = str(parsed)
        elif create_project_id:
            project_id = str(uuid.uuid4())
        elif not allow_legacy:
            raise ValueError(
                "manifest.md is missing a valid UUIDv4 project_id; run "
                "`memory-custodian migrate` or `init --repair`."
            )

        if project_id is None:
            yield ProjectMutationGuard(
                None,
                manifest_text,
                bootstrap_path,
                None,
            )
            return

        with mutation_lock(
            project_id,
            project_root,
            command,
            timeout=timeout,
            break_stale=break_stale,
        ) as project_path:
            yield ProjectMutationGuard(
                project_id,
                manifest_text,
                bootstrap_path,
                project_path,
            )
