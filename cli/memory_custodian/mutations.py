"""Precomputed multi-file text mutation plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat

from .protocol import write_text


@dataclass(frozen=True)
class TextMutation:
    path: Path
    text: str


class PartialMutationError(OSError):
    """Report a failed write together with files already committed."""

    def __init__(self, failed: Path, completed: tuple[Path, ...], cause: OSError):
        super().__init__(str(cause))
        self.failed = failed
        self.completed = completed
        self.__cause__ = cause


def _is_macos_private_alias(path: Path, canonical: Path) -> bool:
    """Allow the system aliases macOS exposes as ``/private/<name>``."""

    if path.anchor != "/" or path.parent != Path("/"):
        return False
    return canonical.parent == Path("/private") and canonical.name == path.name


def _validate_write_target(path: Path) -> None:
    """Reject symlinked targets and ancestors before any directory creation."""

    candidate = path.expanduser().absolute()
    try:
        info = candidate.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Mutation target is not a regular non-symlink file: {path}")

    cursor = candidate.parent
    while True:
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            if cursor == cursor.parent:
                break
            cursor = cursor.parent
            continue
        if stat.S_ISLNK(info.st_mode):
            # Continue to the filesystem root instead of stopping at the
            # first real directory.  A path such as ``docs -> /external``
            # makes ``docs/memory`` look like a normal directory after the
            # symlink is followed, so stopping there would still let an
            # atomic replacement escape the project.  macOS exposes /var
            # (and /tmp, /etc) as aliases to /private; these system aliases
            # are safe and are the only symlinked ancestors exempted here.
            try:
                canonical = cursor.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                raise ValueError(f"Mutation target has an unsafe ancestor: {cursor}") from exc
            if not _is_macos_private_alias(cursor, canonical):
                raise ValueError(f"Mutation target has an unsafe ancestor: {cursor}")
            cursor = cursor.parent
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Mutation target has a non-directory parent: {cursor}")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent


def apply_mutations(mutations: list[TextMutation]) -> tuple[Path, ...]:
    """Validate a complete plan, then apply each atomic file replacement."""

    paths = [mutation.path for mutation in mutations]
    if len(paths) != len(set(paths)):
        raise ValueError("Mutation plan contains the same file more than once.")
    for mutation in mutations:
        _validate_write_target(mutation.path)
        if not isinstance(mutation.text, str):
            raise ValueError(f"Mutation content is not text: {mutation.path}")

    completed: list[Path] = []
    for mutation in mutations:
        try:
            write_text(mutation.path, mutation.text)
        except OSError as exc:
            raise PartialMutationError(mutation.path, tuple(completed), exc) from exc
        completed.append(mutation.path)
    return tuple(completed)
