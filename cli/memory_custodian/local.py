"""CLI operations for the repo-external local overlay."""

from __future__ import annotations

import hashlib
import json
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
    _manifest_text,
)
from .locking import (
    ensure_private_directory,
    project_mutation_guard,
)
from .output import PUBLIC_PLAN_SCHEMA_VERSION, publish_data, publish_finding
from .results import make_finding
from .protocol import (
    ENTRY_SCHEMA_MIGRATION_MESSAGE,
    entry_schema_version_for_manifest,
    entry_schema_migration_available,
    protocol_metadata,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
)
from .snapshot import build_snapshot
from .mutations import PrivateDeleteMutation, PrivateTextMutation
from .transactions import apply_transaction, ensure_no_unfinished_for_project


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
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
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


def _reset_targets(directory: Path) -> tuple[PrivateDeleteMutation, ...]:
    root = directory.parent
    paths = [
        path for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    binding = root / "bindings.json"
    if binding.is_file() and not binding.is_symlink():
        paths.append(binding)
    return tuple(
        PrivateDeleteMutation(path, path.relative_to(root).as_posix())
        for path in sorted(set(paths), key=lambda item: item.as_posix())
    )


def _reset_plan_id(
    project_id: str,
    status: LocalStatus,
    dependencies: list[str],
    blockers: list[str],
) -> str:
    seed = "\0".join([
        "local-reset",
        project_id,
        status.value,
        *dependencies,
        *(f"blocker:{item}" for item in blockers),
    ]).encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:16]


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = memory_dir / "manifest.md"
    if not manifest.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    manifest_text = read_managed_text(memory_dir, manifest)
    entry_schema_version = entry_schema_version_for_manifest(manifest_text)
    command = args.local_command
    # Status and reset are read-only diagnostics in Protocol 0.7.  They may
    # inspect a distributed schema-1 overlay with its legacy body grammar so
    # the migration warning is actionable.  Enable/link/add remain mutation
    # gates and must reject the schema-1 manifest before touching local state.
    allow_legacy_entry_schema = command in {"status", "reset"}
    project_id = validated_project_identity(
        memory_dir,
        manifest_text=manifest_text,
        allow_legacy_entry_schema=allow_legacy_entry_schema,
    )
    if allow_legacy_entry_schema and entry_schema_migration_available(
        protocol_metadata(manifest_text)
    ):
        publish_finding(make_finding(
            "MC-MIGRATION-001",
            "WARNING",
            ENTRY_SCHEMA_MIGRATION_MESSAGE,
            path="docs/memory/manifest.md",
            remediation="Run the staged migration after reviewing its preview.",
        ))
        print(ENTRY_SCHEMA_MIGRATION_MESSAGE)
    if command == "status":
        shared_ids = memory_entry_ids(memory_dir)
        render_overlay_status(inspect_overlay(
            project_root,
            project_id,
            shared_ids=shared_ids,
            entry_schema_version=entry_schema_version,
        ))
        return 0
    if command == "reset":
        shared_ids = memory_entry_ids(memory_dir)
        overlay = inspect_overlay(
            project_root,
            project_id,
            shared_ids=shared_ids,
            entry_schema_version=entry_schema_version,
        )
        render_overlay_status(overlay)
        if overlay.status == LocalStatus.DISABLED:
            print("No local overlay state exists for this project; nothing to reset.")
            render_scope(ErasureScope(
                erasure_scope_schema_version=1,
                operation_phase="no-op",
                active_memory="not-applicable",
                managed_archive="not-targeted",
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
        plan_id = _reset_plan_id(project_id, overlay.status, dependencies, blockers)
        publish_data(plan={
            "public_plan_schema_version": PUBLIC_PLAN_SCHEMA_VERSION,
            "plan_id": plan_id,
            "readiness": "blocked" if blockers else "ready",
            "targets": [{"path": "local/", "operation": "delete"}],
            "blockers": list(blockers),
            "warnings": [],
            "budget_results": [],
        })
        print(f"Plan ID: {plan_id}")
        print("Blockers:")
        for blocker in blockers or ["none"]:
            print(f"- {blocker}")
        reset_scope = ErasureScope(
            erasure_scope_schema_version=1,
            operation_phase="preview",
            active_memory="not-applicable",
            managed_archive="not-targeted",
            local_overlay="pending-removal",
            git_worktree_modified="no",
            git_history_modified=False,
            distributed_copies_revoked=False,
            history_check_status="not-requested",
            topic_retained_in_new_records=False,
        )
        render_scope(reset_scope)
        if not args.apply:
            print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
            return 0
        if blockers:
            print("Refusing local reset while blockers remain.")
            return 1
        if args.confirm_plan != plan_id:
            raise ValueError("Stale or mismatched local reset plan.")
        assert overlay.directory is not None
        with project_mutation_guard(
            project_root, manifest, "local reset",
            timeout=args.lock_timeout, break_stale=args.break_stale_lock,
        ) as guard:
            if guard.project_id != project_id:
                raise ValueError("Project identity changed before local reset; preview again.")
            locked_overlay = inspect_overlay(
                project_root,
                project_id,
                shared_ids=memory_entry_ids(memory_dir),
                entry_schema_version=entry_schema_version,
            )
            locked_dependencies, locked_blockers = _reset_inventory(locked_overlay.directory)
            if locked_overlay.status in {LocalStatus.UNBOUND, LocalStatus.REVIEW}:
                locked_blockers.extend(locked_overlay.warnings)
            locked_plan_id = _reset_plan_id(
                project_id,
                locked_overlay.status,
                locked_dependencies,
                locked_blockers,
            )
            if locked_plan_id != args.confirm_plan:
                raise ValueError("Local overlay changed before reset apply; preview again.")
            if locked_blockers or locked_overlay.directory is None:
                raise ValueError("Local overlay is no longer safe to reset.")
            targets = _reset_targets(locked_overlay.directory)
            child_directories = tuple(
                item for item in locked_overlay.directory.rglob("*") if item.is_dir()
            )
            directories = tuple(
                sorted(
                    (locked_overlay.directory, *child_directories),
                    key=lambda item: item.as_posix(),
                )
            )
            apply_transaction(
                project_root=project_root, memory_root=memory_dir,
                project_id=project_id, command="local-reset", plan_id=plan_id,
                private_deletions=targets, local_root=locked_overlay.directory.parent,
                remove_directories=directories,
                erasure_scope=reset_scope.canonical(),
                force_journal=True,
            )
        render_scope(ErasureScope(
            erasure_scope_schema_version=1,
            operation_phase="applied",
            active_memory="not-applicable",
            managed_archive="not-targeted",
            local_overlay="removed",
            git_worktree_modified="no",
            git_history_modified=False,
            distributed_copies_revoked=False,
            history_check_status="not-requested",
            topic_retained_in_new_records=False,
        ))
        print("Removed the current machine/project local overlay only; other machines and backups were not modified.")
        return 0

    with project_mutation_guard(
        project_root,
        manifest,
        f"local {command}",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
    ) as mutation:
        # The initial identity check above is only command routing.  Once the
        # project lock is held, rebuild the shared snapshot and derive every
        # ID-safety decision from that captured, lock-internal view.  A shared
        # Entry created while the lock was being acquired must therefore
        # reserve its ID before local allocation proceeds.
        locked_project_id = mutation.project_id
        if locked_project_id is None:
            raise ValueError("Local overlay access requires a valid Protocol 0.8 project identity.")
        locked_snapshot = build_snapshot(memory_dir, project_root)
        captured_project_id = validated_project_identity(
            memory_dir,
            manifest_text=locked_snapshot.manifest_text,
        )
        if captured_project_id != locked_project_id:
            raise ValueError("Project manifest changed while acquiring the mutation lock.")
        # Even single-file local mutations must not race an interrupted
        # shared/local transaction for the same project identity.
        ensure_no_unfinished_for_project(
            project_root, memory_dir, (locked_project_id,)
        )
        shared_ids = {
            entry.entry_id for entry in locked_snapshot.relation_entries
        }
        if command in {"enable", "link"}:
            overlay = inspect_overlay(
                project_root,
                locked_project_id,
                shared_ids=shared_ids,
                entry_schema_version=locked_snapshot.entry_schema_version,
                capture_unbound=True,
            )
        if command == "enable":
            if overlay.status == LocalStatus.DISABLED:
                if overlay.directory is None:
                    raise ValueError("Local overlay enable has no safe target directory.")
                # The project-id directory is the trusted root for this
                # transaction.  It is private infrastructure rather than a
                # transaction target, so establish and validate it before
                # the journal inventories the missing ``local/`` subtree.
                local_root = ensure_private_directory(overlay.directory.parent)
                private_mutations = (
                    PrivateTextMutation(overlay.directory / "manifest.md", "manifest.md", _manifest_text(locked_project_id)),
                    PrivateTextMutation(
                        overlay.directory / "preferences.md", "preferences.md",
                        "# Local Preferences\n\nEntries are newest first.\n",
                    ),
                )
                plan_id = hashlib.sha256(
                    ("local-enable\0" + locked_project_id).encode("utf-8")
                ).hexdigest()[:16]
                apply_transaction(
                    project_root=project_root, memory_root=memory_dir,
                    project_id=locked_project_id, command="local-enable", plan_id=plan_id,
                    private_mutations=private_mutations, local_root=local_root,
                    private_directories=(overlay.directory / "profiles",),
                    force_journal=True,
                )
                overlay = inspect_overlay(
                    project_root, locked_project_id, shared_ids=shared_ids,
                    entry_schema_version=locked_snapshot.entry_schema_version,
                    capture_unbound=True,
                )
            else:
                overlay = enable_overlay(
                    project_root,
                    locked_project_id,
                    shared_ids=shared_ids,
                    entry_schema_version=locked_snapshot.entry_schema_version,
                    overlay=overlay,
                )
            if overlay.directory is None:
                raise ValueError("Local overlay enable did not produce a usable directory.")
            print(f"Local overlay enabled for project_id {locked_project_id}.")
            print(f"State directory: {overlay.directory}")
            print("Run `memory-custodian local link` before local content can load.")
            return 0
        if command == "link":
            if overlay.status == LocalStatus.DISABLED:
                if overlay.directory is None:
                    raise ValueError("Local overlay link has no safe target directory.")
                local_root = ensure_private_directory(overlay.directory.parent)
                current_root = str(project_root.resolve())
                binding_path = local_root / "bindings.json"
                private_mutations = (
                    PrivateTextMutation(
                        overlay.directory / "manifest.md",
                        "local/manifest.md",
                        _manifest_text(locked_project_id),
                    ),
                    PrivateTextMutation(
                        overlay.directory / "preferences.md",
                        "local/preferences.md",
                        "# Local Preferences\n\nEntries are newest first.\n",
                    ),
                    PrivateTextMutation(
                        binding_path,
                        "bindings.json",
                        json.dumps(
                            {"project_id": locked_project_id, "roots": [current_root]},
                            sort_keys=True,
                            indent=2,
                        ) + "\n",
                    ),
                )
                plan_id = hashlib.sha256(
                    ("local-link\0" + locked_project_id + "\0" + current_root).encode("utf-8")
                ).hexdigest()[:16]
                apply_transaction(
                    project_root=project_root,
                    memory_root=memory_dir,
                    project_id=locked_project_id,
                    command="local-link",
                    plan_id=plan_id,
                    private_mutations=private_mutations,
                    private_directories=(overlay.directory / "profiles",),
                    local_root=local_root,
                    force_journal=True,
                )
                roots = (current_root,)
            else:
                overlay = enable_overlay(
                    project_root,
                    locked_project_id,
                    shared_ids=shared_ids,
                    entry_schema_version=locked_snapshot.entry_schema_version,
                    overlay=overlay,
                )
                roots = link_root(
                    project_root,
                    locked_project_id,
                    shared_ids=shared_ids,
                    entry_schema_version=locked_snapshot.entry_schema_version,
                    overlay=overlay,
                )
            print("Local overlay linked to this normalized project root.")
            if len(roots) > 1:
                publish_finding(make_finding(
                    "MC-LOCAL-001",
                    "WARNING",
                    "The same project_id is explicitly bound to multiple roots.",
                    path="local/",
                    remediation="Review and remove obsolete explicit root bindings.",
                ))
                print("Local overlay status: REVIEW")
                print("The same project_id is explicitly bound to multiple roots.")
            return 0
        if command == "add":
            if args.type != "preference":
                raise ValueError("Protocol 0.8 local add currently supports --type preference only.")
            evidence = validate_evidence(args.evidence, project_root)
            entry_id = add_local_preference(
                project_root,
                locked_project_id,
                args.message,
                evidence,
                shared_ids=shared_ids,
                entry_schema_version=locked_snapshot.entry_schema_version,
            )
            print(f"Added local preference {entry_id}.")
            return 0
    raise ValueError(f"Unknown local command: {command}")
