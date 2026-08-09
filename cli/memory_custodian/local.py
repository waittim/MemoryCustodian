"""CLI operations for the repo-external local overlay."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from .entries import memory_entry_ids, validate_evidence
from .erasure import ErasureScope, render_scope
from .local_overlay import (
    LocalStatus,
    add_local_preference,
    enable_overlay,
    inspect_overlay,
    link_root,
    render_overlay_status,
    validated_project_identity,
)
from .locking import (
    project_mutation_guard,
)
from .protocol import resolve_memory_dir, resolve_project_root


def _reset_inventory(
    directory: Path | None,
) -> tuple[list[str], list[str]]:
    """Hash private state bytes without following unsafe filesystem nodes."""

    dependencies: list[str] = []
    blockers: list[str] = []
    if directory is None:
        return ["local:unsafe-root"], ["Unsafe local overlay root requires review."]
    root_missing = False
    try:
        root_metadata = directory.lstat()
        if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
            raise OSError("local overlay root is not a real directory")
        if hasattr(os, "getuid") and root_metadata.st_uid != os.getuid():
            raise OSError("local overlay root is not owned by the current user")
        if os.name != "nt" and stat.S_IMODE(root_metadata.st_mode) != 0o700:
            raise OSError("local overlay root must use mode 0700")
    except FileNotFoundError:
        root_missing = True
        dependencies.append("local:missing-root")
        blockers.append("Local overlay binding is orphaned because the local directory is missing.")
    except OSError as exc:
        return ["local:unsafe-root"], [f"Unsafe local overlay root requires review: {exc}"]
    paths: list[Path] = []
    walk_errors: list[OSError] = []
    if not root_missing:
        for root, directories, files in os.walk(
            directory,
            followlinks=False,
            onerror=walk_errors.append,
        ):
            root_path = Path(root)
            paths.extend(root_path / name for name in directories)
            paths.extend(root_path / name for name in files)
    binding_path = directory.parent / "bindings.json"
    if binding_path.exists() or binding_path.is_symlink():
        paths.append(binding_path)
    for error in walk_errors:
        location = error.filename or "unknown"
        dependencies.append(f"walk-error:{location}:{error.errno}")
        blockers.append(f"Cannot traverse local overlay state: {location}: {error}")
    for path in sorted(set(paths)):
        relative = path.relative_to(directory.parent).as_posix()
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                target = os.readlink(path)
                dependencies.append(
                    f"{relative}:symlink:{hashlib.sha256(target.encode('utf-8')).hexdigest()}"
                )
                blockers.append(f"Unsafe local overlay symlink requires review: {relative}")
                continue
            if stat.S_ISDIR(metadata.st_mode):
                mode = stat.S_IMODE(metadata.st_mode)
                dependencies.append(f"{relative}:directory:{mode:o}")
                if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
                    blockers.append(
                        f"Unsafe local overlay directory owner requires review: {relative}"
                    )
                if os.name != "nt" and mode != 0o700:
                    blockers.append(
                        f"Unreadable local overlay directory requires review: {relative}; "
                        "private directories must use mode 0700"
                    )
                continue
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode):
                    raise OSError("private state node is not a regular file")
                if hasattr(os, "getuid") and opened.st_uid != os.getuid():
                    raise OSError("private state file is not owned by the current user")
                if os.name != "nt" and stat.S_IMODE(opened.st_mode) != 0o600:
                    raise OSError("private state file must use mode 0600")
                digestor = hashlib.sha256()
                while True:
                    chunk = os.read(descriptor, 64 * 1024)
                    if not chunk:
                        break
                    digestor.update(chunk)
                digest = digestor.hexdigest()
            finally:
                os.close(descriptor)
            dependencies.append(f"{relative}:file:{digest}")
        except (OSError, ValueError) as exc:
            dependencies.append(f"{relative}:unreadable")
            blockers.append(f"Unsafe local overlay state requires review: {relative}: {exc}")
    return dependencies, blockers


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = memory_dir / "manifest.md"
    if not manifest.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    project_id = validated_project_identity(memory_dir)
    shared_ids = memory_entry_ids(memory_dir)
    command = args.local_command
    if command == "status":
        render_overlay_status(inspect_overlay(project_root, project_id, shared_ids=shared_ids))
        return 0
    if command == "reset":
        overlay = inspect_overlay(project_root, project_id, shared_ids=shared_ids)
        render_overlay_status(overlay)
        if overlay.status == LocalStatus.DISABLED:
            print("No local overlay state exists for this project; nothing to reset.")
            render_scope(ErasureScope(
                active_memory=False,
                managed_archive=False,
                local_overlay="not-applicable",
                git_worktree_modified="no",
                git_history_modified=False,
                distributed_copies_revoked=False,
                history_check_status="not-requested",
                topic_retained_in_new_records=False,
            ))
            return 0
        dependencies, inventory_blockers = _reset_inventory(overlay.directory)
        blockers = list(inventory_blockers)
        if overlay.status in {LocalStatus.UNBOUND, LocalStatus.REVIEW}:
            blockers.extend(overlay.warnings)
        seed = "\0".join([
            "local-reset",
            project_id,
            overlay.status.value,
            *dependencies,
            *(f"blocker:{item}" for item in blockers),
        ]).encode("utf-8")
        print(f"Plan ID: {hashlib.sha256(seed).hexdigest()[:16]}")
        print("Blockers:")
        for blocker in blockers or ["none"]:
            print(f"- {blocker}")
        render_scope(ErasureScope(
            active_memory=False,
            managed_archive=False,
            local_overlay=(
                "blocked-pending-local-overlay-review"
                if blockers
                else "current-machine-current-project-on-protocol-0.8-apply"
            ),
            git_worktree_modified="no",
            git_history_modified=False,
            distributed_copies_revoked=False,
            history_check_status="not-requested",
            topic_retained_in_new_records=False,
        ))
        print("Transactional local reset apply requires Protocol 0.8.")
        return 0

    with project_mutation_guard(
        project_root,
        manifest,
        f"local {command}",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
    ):
        if command == "enable":
            directory = enable_overlay(project_root, project_id, shared_ids=shared_ids)
            print(f"Local overlay enabled for project_id {project_id}.")
            print(f"State directory: {directory}")
            print("Run `memory-custodian local link` before local content can load.")
            return 0
        if command == "link":
            enable_overlay(project_root, project_id, shared_ids=shared_ids)
            roots = link_root(project_root, project_id, shared_ids=shared_ids)
            print("Local overlay linked to this normalized project root.")
            if len(roots) > 1:
                print("Local overlay status: REVIEW")
                print("The same project_id is explicitly bound to multiple roots.")
            return 0
        if command == "add":
            if args.type != "preference":
                raise ValueError("Protocol 0.7 local add currently supports --type preference only.")
            evidence = validate_evidence(args.evidence, project_root)
            entry_id = add_local_preference(
                project_root,
                project_id,
                args.message,
                evidence,
                shared_ids=shared_ids,
            )
            print(f"Added local preference {entry_id}.")
            return 0
    raise ValueError(f"Unknown local command: {command}")
