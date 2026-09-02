"""Precomputed multi-file text mutation plans."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tempfile

from .locking import write_private_file
from .protocol import write_text


@dataclass(frozen=True)
class TextMutation:
    path: Path
    text: str


@dataclass(frozen=True)
class PrivateTextMutation:
    """One private-state replacement whose public path is an alias.

    Repo-relative ``TextMutation`` paths are intentionally unsuitable for the
    repo-external local overlay.  Keep the real path for the secure writer and
    a stable relative label for plan rendering/digests.
    """

    path: Path
    relative: str
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


def restore_text_file_exact(path: Path, text: str | None) -> None:
    """Restore an exact UTF-8 text preimage without adding a newline.

    Migration recovery needs a byte-faithful restore for files that may use
    CRLF, trailing spaces, or no terminal newline.  Keep this helper separate
    from the normal writer, whose public contract intentionally normalizes a
    terminal newline.  ``None`` means the file did not exist and should be
    removed if a failed migration created it.
    """

    candidate = path.expanduser().absolute()
    _validate_write_target(candidate)
    if text is None:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Mutation recovery target is not a regular non-symlink file: {path}")
        candidate.unlink()
        return

    try:
        mode = stat.S_IMODE(candidate.lstat().st_mode)
    except FileNotFoundError:
        mode = 0o644
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=candidate.parent,
            prefix=f".{candidate.name}.",
            suffix=".restore.tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text.encode("utf-8"))
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.chmod(temporary, mode)
        os.replace(temporary, candidate)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def apply_private_mutations(
    mutations: list[PrivateTextMutation],
) -> tuple[Path, ...]:
    """Apply private overlay replacements through the owner-only writer."""

    paths = [mutation.path for mutation in mutations]
    if len(paths) != len(set(paths)):
        raise ValueError("Private mutation plan contains the same file more than once.")
    completed: list[Path] = []
    for mutation in mutations:
        if not isinstance(mutation.text, str):
            raise ValueError(f"Private mutation content is not text: {mutation.path}")
        try:
            write_private_file(mutation.path, mutation.text)
        except OSError as exc:
            raise PartialMutationError(
                mutation.path,
                tuple(completed),
                exc,
            ) from exc
        completed.append(mutation.path)
    return tuple(completed)
