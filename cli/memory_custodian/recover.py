"""Analyze, complete, or roll back interrupted mutation transactions."""

from __future__ import annotations

from pathlib import Path

from .erasure import ErasureScope, render_scope
from .local_overlay import overlay_directory
from .locking import private_state_directory, project_mutation_guard
from .protocol import (
    project_id_from_manifest,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
)
from .transactions import (
    RootBinding,
    analyze_transaction,
    existing_binding_directories,
    load_journal,
    recover_transaction,
    unfinished_transaction_directories,
)


def _bindings(project_root: Path, memory_dir: Path, project_id: str | None) -> tuple[Path, ...]:
    return existing_binding_directories(
        project_root,
        memory_dir,
        (project_id,) if project_id else (),
    )


def _roots(project_root: Path, project_id: str | None) -> dict[str, RootBinding]:
    values = {
        "shared": RootBinding("shared", project_root.absolute(), "shared"),
        "migration-state": RootBinding(
            "migration-state", private_state_directory("migrations").absolute(),
            "migration-state",
        ),
    }
    if project_id:
        values["local-overlay"] = RootBinding(
            "local-overlay", overlay_directory(project_id).parent.absolute(), "local"
        )
    return values


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest_path = memory_dir / "manifest.md"
    manifest = (
        read_managed_text(memory_dir, manifest_path)
        if manifest_path.exists() else ""
    )
    project_id = project_id_from_manifest(manifest, required=False) if manifest else None
    action = "complete" if args.complete else "rollback" if args.rollback else None

    with project_mutation_guard(
        project_root,
        manifest_path,
        "recover",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
        allow_legacy=True,
    ):
        directories = tuple(
            directory
            for binding in _bindings(project_root, memory_dir, project_id)
            for directory in unfinished_transaction_directories(binding)
        )
        if not directories:
            print("Transactions: clean")
            return 0
        if args.transaction_id:
            selected = [item for item in directories if item.name == args.transaction_id]
            if not selected:
                raise ValueError("Requested transaction ID is not an unfinished transaction for this project.")
        else:
            selected = list(directories)
        if action and not args.transaction_id:
            raise ValueError("Recovery apply requires --transaction-id with --complete or --rollback.")

        roots = _roots(project_root, project_id)
        records = [analyze_transaction(item, roots) for item in selected]
        if action:
            selected_record = records[0]
            action_is_safe = (
                selected_record.safe_complete
                if action == "complete"
                else selected_record.safe_rollback
            )
            if not action_is_safe:
                # Keep the mutation guard and error contract centralized in
                # recover_transaction.  In particular, do not parse optional
                # metadata from a journal that analysis already rejected.
                recover_transaction(selected[0], roots, action=action)
            journal = load_journal(selected[0])
            stored_scope = journal.get("erasure_scope")
            record = recover_transaction(selected[0], roots, action=action)
            print(f"Transaction {record.transaction_id}: {record.phase}")
            if isinstance(stored_scope, dict):
                restored = action == "rollback"
                def recovered_domain(value: object) -> str:
                    if value == "pending-removal":
                        return "restored" if restored else "removed"
                    return str(value)
                try:
                    render_scope(ErasureScope(
                        erasure_scope_schema_version=int(stored_scope["erasure_scope_schema_version"]),
                        operation_phase=("recovered-rollback" if restored else "recovered-complete"),
                        active_memory=recovered_domain(stored_scope["active_memory"]),
                        managed_archive=recovered_domain(stored_scope["managed_archive"]),
                        local_overlay=recovered_domain(stored_scope["local_overlay"]),
                        git_worktree_modified="yes",
                        git_history_modified=False,
                        distributed_copies_revoked=False,
                        history_check_status=str(stored_scope["history_check_status"]),
                        topic_retained_in_new_records=bool(stored_scope["topic_retained_in_new_records"]),
                    ))
                except (KeyError, TypeError, ValueError):
                    print("Erasure scope metadata requires manual audit.")
            if action == "rollback" and record.command in {"forget-hard", "forget-purge", "forget"}:
                print("Managed content was restored from protected recovery state.")
            return 0

        print("Transactions: recovery required")
        for record in records:
            print(f"- {record.transaction_id}")
            print(f"  Phase: {record.phase}")
            print(f"  Operation: {record.command}")
            print(f"  Complete safe: {'yes' if record.safe_complete else 'no'}")
            print(f"  Rollback safe: {'yes' if record.safe_rollback else 'no'}")
            for issue in record.issues:
                print(f"  Issue: {issue}")
        if len(records) > 1:
            print("Select one opaque transaction ID before applying recovery.")
        return 2 if any(record.phase == "invalid" for record in records) else 0
