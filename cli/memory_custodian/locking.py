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
        payload = json.loads(read_private_file(path))
        age = time.time() - path.stat().st_mtime
        return (
            payload.get("hostname") == socket.gethostname()
            and not _pid_exists(int(payload.get("pid", -1)))
            and age > minimum_age
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


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
        except FileNotFoundError:
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
            from .protocol import project_id_from_manifest

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
