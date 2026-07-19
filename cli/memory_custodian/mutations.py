"""Precomputed multi-file text mutation plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def apply_mutations(mutations: list[TextMutation]) -> tuple[Path, ...]:
    """Validate a complete plan, then apply each atomic file replacement."""

    paths = [mutation.path for mutation in mutations]
    if len(paths) != len(set(paths)):
        raise ValueError("Mutation plan contains the same file more than once.")
    for mutation in mutations:
        if mutation.path.exists() and not mutation.path.is_file():
            raise ValueError(f"Mutation target is not a regular file: {mutation.path}")
        ancestor = mutation.path.parent
        while not ancestor.exists():
            parent = ancestor.parent
            if parent == ancestor:
                break
            ancestor = parent
        if ancestor.exists() and not ancestor.is_dir():
            raise ValueError(f"Mutation target has a non-directory parent: {ancestor}")
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
