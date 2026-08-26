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
            raise ValueError(f"Mutation target has an unsafe ancestor: {cursor}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Mutation target has a non-directory parent: {cursor}")
        break


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
