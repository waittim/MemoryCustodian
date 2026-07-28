"""Project-scoped mutation locks stored outside repositories."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import tempfile
import time


class LockError(OSError):
    pass


def state_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "MemoryCustodian" / "state" if base else Path(tempfile.gettempdir()) / "memory-custodian-state"
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "memory-custodian"
    try:
        return Path.home() / ".local" / "state" / "memory-custodian"
    except RuntimeError:
        return Path(tempfile.gettempdir()) / "memory-custodian-state"


def lock_path(project_id: str) -> Path:
    return state_root() / "locks" / f"{project_id}.lock"


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
        payload = json.loads(path.read_text(encoding="utf-8"))
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
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir()) / "memory-custodian-state" / "locks" / f"{project_id}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    payload = {
        "project_id": project_id,
        "project_root": str(project_root),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
    }
    used_fallback = str(path).startswith(tempfile.gettempdir())
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True)
            break
        except PermissionError:
            if used_fallback:
                raise
            path = Path(tempfile.gettempdir()) / "memory-custodian-state" / "locks" / f"{project_id}.lock"
            path.parent.mkdir(parents=True, exist_ok=True)
            used_fallback = True
            continue
        except FileExistsError:
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
            current = json.loads(path.read_text(encoding="utf-8"))
            if current.get("pid") == os.getpid():
                path.unlink()
        except FileNotFoundError:
            pass
