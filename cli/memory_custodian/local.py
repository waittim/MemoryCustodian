"""CLI operations for the repo-external local overlay."""

from __future__ import annotations

import hashlib

from .entries import validate_evidence
from .erasure import ErasureScope, render_scope
from .local_overlay import (
    add_local_preference,
    enable_overlay,
    inspect_overlay,
    link_root,
    project_identity,
    render_overlay_status,
)
from .locking import project_mutation_guard
from .protocol import resolve_memory_dir, resolve_project_root


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = memory_dir / "manifest.md"
    if not manifest.exists():
        raise ValueError("manifest.md is missing; the MemoryCustodian setup is incomplete or corrupted")
    project_id = project_identity(memory_dir)
    command = args.local_command
    if command == "status":
        render_overlay_status(inspect_overlay(project_root, project_id))
        return 0
    if command == "reset":
        overlay = inspect_overlay(project_root, project_id)
        render_overlay_status(overlay)
        seed = f"local-reset\0{project_id}\0{overlay.status.value}".encode("utf-8")
        print(f"Plan ID: {hashlib.sha256(seed).hexdigest()[:16]}")
        render_scope(ErasureScope(
            active_memory=False,
            managed_archive=False,
            local_overlay="current-machine-current-project-on-protocol-0.8-apply",
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
            directory = enable_overlay(project_id)
            print(f"Local overlay enabled for project_id {project_id}.")
            print(f"State directory: {directory}")
            print("Run `memory-custodian local link` before local content can load.")
            return 0
        if command == "link":
            enable_overlay(project_id)
            roots = link_root(project_root, project_id)
            print("Local overlay linked to this normalized project root.")
            if len(roots) > 1:
                print("Local overlay status: REVIEW")
                print("The same project_id is explicitly bound to multiple roots.")
            return 0
        if command == "add":
            if args.type != "preference":
                raise ValueError("Protocol 0.7 local add currently supports --type preference only.")
            evidence = validate_evidence(args.evidence, project_root)
            entry_id = add_local_preference(project_root, project_id, args.message, evidence)
            print(f"Added local preference {entry_id}.")
            return 0
    raise ValueError(f"Unknown local command: {command}")
