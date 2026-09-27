"""Analyze, complete, or roll back interrupted mutation transactions."""

from __future__ import annotations

from pathlib import Path

from .erasure import ErasureScope, render_scope
from .local_overlay import overlay_directory
from .locking import private_state_directory, project_mutation_guard
from .output import publish_data
from .protocol import (
    project_id_from_manifest,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
)
from .transactions import (
    RecoveryTargetState,
    RootBinding,
    analyze_transaction,
    existing_binding_directories,
    load_journal,
    recover_transaction,
    unfinished_transaction_directories,
)


_ERASURE_DOMAIN_VALUES = frozenset({
    "not-targeted", "no-match", "pending-removal", "removed", "restored",
    "not-applicable",
})
_HISTORY_CHECK_VALUES = frozenset({
    "not-requested", "unavailable", "reachable-copy-detected",
    "no-reachable-copy-detected",
})


def _recovered_scope(
    stored_scope: object,
    target_states: tuple[RecoveryTargetState, ...],
    roots: dict[str, RootBinding],
    memory_dir: Path,
    *,
    action: str,
) -> ErasureScope:
    """Build public erasure effects from validated pre-recovery target state."""

    if not isinstance(stored_scope, dict):
        raise ValueError("Erasure scope metadata is malformed.")
    try:
        scope = ErasureScope(
            erasure_scope_schema_version=int(stored_scope["erasure_scope_schema_version"]),
            operation_phase="recovered-complete" if action == "complete" else "recovered-rollback",
            active_memory=str(stored_scope["active_memory"]),
            managed_archive=str(stored_scope["managed_archive"]),
            local_overlay=str(stored_scope["local_overlay"]),
            git_worktree_modified=str(stored_scope["git_worktree_modified"]),
            git_history_modified=stored_scope["git_history_modified"],
            distributed_copies_revoked=stored_scope["distributed_copies_revoked"],
            history_check_status=str(stored_scope["history_check_status"]),
            topic_retained_in_new_records=stored_scope["topic_retained_in_new_records"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Erasure scope metadata is malformed.") from exc
    if (
        type(stored_scope.get("erasure_scope_schema_version")) is not int
        or scope.erasure_scope_schema_version != 1
        or scope.active_memory not in _ERASURE_DOMAIN_VALUES
        or scope.managed_archive not in _ERASURE_DOMAIN_VALUES
        or scope.local_overlay not in _ERASURE_DOMAIN_VALUES
        or scope.git_worktree_modified not in {"no", "on-apply", "yes"}
        or scope.history_check_status not in _HISTORY_CHECK_VALUES
        or not isinstance(scope.git_history_modified, bool)
        or not isinstance(scope.distributed_copies_revoked, bool)
        or not isinstance(scope.topic_retained_in_new_records, bool)
        or scope.git_history_modified is not False
        or scope.distributed_copies_revoked is not False
    ):
        raise ValueError("Erasure scope metadata is malformed.")

    targets_by_domain: dict[str, list[RecoveryTargetState]] = {
        "active_memory": [],
        "managed_archive": [],
        "local_overlay": [],
    }
    for target in target_states:
        if target.root_kind == "local-overlay":
            domain = "local_overlay"
        elif target.root_kind == "shared":
            binding = roots.get("shared")
            if binding is None:
                continue
            target_path = binding.root / target.path
            try:
                relative = target_path.relative_to(memory_dir)
            except ValueError:
                continue
            domain = (
                "managed_archive"
                if relative.parts and relative.parts[0] == "archive"
                else "active_memory"
            )
        else:
            continue
        targets_by_domain[domain].append(target)

    updated_domains: dict[str, str] = {}
    for name in targets_by_domain:
        current = getattr(scope, name)
        targets = targets_by_domain[name]
        if current != "pending-removal":
            updated_domains[name] = current
            continue
        if not targets or any(target.state not in {"base", "output"} for target in targets):
            raise ValueError("Erasure scope targets require manual audit.")
        if action == "complete":
            updated_domains[name] = (
                "removed"
                if any(target.content_differs_from_base for target in targets)
                else "pending-removal"
            )
        else:
            updated_domains[name] = (
                "restored"
                if any(
                    target.state == "output" and target.content_differs_from_base
                    for target in targets
                )
                else "pending-removal"
            )

    scoped_targets = (
        target
        for targets in targets_by_domain.values()
        for target in targets
    )
    worktree_changed = any(
        target.root_kind == "shared"
        and target.output_differs_from_base
        and (
            (action == "complete" and target.state == "base")
            or (action == "rollback" and target.state == "output")
        )
        for target in scoped_targets
    )
    return ErasureScope(
        erasure_scope_schema_version=scope.erasure_scope_schema_version,
        operation_phase=scope.operation_phase,
        active_memory=updated_domains["active_memory"],
        managed_archive=updated_domains["managed_archive"],
        local_overlay=updated_domains["local_overlay"],
        git_worktree_modified="yes" if worktree_changed else "no",
        git_history_modified=scope.git_history_modified,
        distributed_copies_revoked=scope.distributed_copies_revoked,
        history_check_status=scope.history_check_status,
        topic_retained_in_new_records=scope.topic_retained_in_new_records,
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
            publish_data(recovery_status="clean", transactions=[])
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
            publish_data(
                recovery_status=record.phase,
                transactions=[{
                    "transaction_id": record.transaction_id,
                    "phase": record.phase,
                    "operation": record.command,
                }],
            )
            print(f"Transaction {record.transaction_id}: {record.phase}")
            recovered_scope: ErasureScope | None = None
            if "erasure_scope" in journal:
                try:
                    recovered_scope = _recovered_scope(
                        stored_scope,
                        record.target_states,
                        roots,
                        memory_dir,
                        action=action,
                    )
                    render_scope(recovered_scope)
                except ValueError:
                    print("Erasure scope metadata requires manual audit.")
            if action == "rollback" and record.command in {"forget-hard", "forget-purge", "forget"}:
                if recovered_scope and (
                    recovered_scope.active_memory == "restored"
                    or recovered_scope.managed_archive == "restored"
                ):
                    print("Managed content was restored from protected recovery state.")
                elif recovered_scope and (
                    recovered_scope.active_memory == "pending-removal"
                    or recovered_scope.managed_archive == "pending-removal"
                ):
                    print(
                        "Managed content was unchanged by the interrupted transaction; "
                        "start a new forget plan if removal is still intended."
                    )
            elif (
                action == "complete"
                and record.command in {"forget-hard", "forget-purge", "forget"}
            ):
                if recovered_scope and (
                    recovered_scope.active_memory == "pending-removal"
                    or recovered_scope.managed_archive == "pending-removal"
                ):
                    print(
                        "No managed content was removed during recovery; start a new "
                        "forget plan if removal is still intended."
                    )
            return 0

        publish_data(
            recovery_status="recovery-required",
            transactions=[{
                "transaction_id": record.transaction_id,
                "phase": record.phase,
                "operation": record.command,
                "complete_safe": record.safe_complete,
                "rollback_safe": record.safe_rollback,
                "issues": list(record.issues),
            } for record in records],
        )
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
