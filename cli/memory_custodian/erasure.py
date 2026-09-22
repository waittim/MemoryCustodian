"""Structured forgetting scope with explicit non-erasure boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass

ERASURE_SCOPE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ErasureScope:
    erasure_scope_schema_version: int
    operation_phase: str
    active_memory: str
    managed_archive: str
    local_overlay: str
    git_worktree_modified: str
    git_history_modified: bool
    distributed_copies_revoked: bool
    history_check_status: str
    topic_retained_in_new_records: bool

    def canonical(self) -> dict[str, object]:
        return asdict(self)


def scope_for_forget(
    mode: str,
    *,
    active_matches: bool,
    archive_matches: bool,
    has_mutations: bool,
    history_check_status: str = "not-requested",
    operation_phase: str = "preview",
) -> ErasureScope:
    applied = operation_phase in {"applied", "recovered-complete"}
    domain = lambda matched: (
        "removed" if matched and applied else
        "pending-removal" if matched else
        "no-match"
    )
    return ErasureScope(
        erasure_scope_schema_version=ERASURE_SCOPE_SCHEMA_VERSION,
        operation_phase=operation_phase,
        active_memory=domain(active_matches),
        managed_archive=(domain(archive_matches) if mode == "purge" else "not-targeted"),
        local_overlay="not-applicable",
        git_worktree_modified=(
            "yes" if applied and has_mutations
            else "on-apply" if operation_phase == "preview" and has_mutations
            else "no"
        ),
        git_history_modified=False,
        distributed_copies_revoked=False,
        history_check_status=history_check_status,
        topic_retained_in_new_records=mode == "soft",
    )


def render_scope(scope: ErasureScope) -> None:
    print("Removal scope:")
    print(f"- Schema: {scope.erasure_scope_schema_version}")
    print(f"- Operation phase: {scope.operation_phase}")
    print(f"- Active managed memory: {scope.active_memory}")
    print(f"- Managed archive: {scope.managed_archive}")
    print(
        "- New tombstones/logs retain topic: "
        + ("yes" if scope.topic_retained_in_new_records else "no")
    )
    print(f"- Local overlay: {scope.local_overlay}")
    print(f"- Git worktree modified: {scope.git_worktree_modified}")
    print(f"- Git history modified: {'yes' if scope.git_history_modified else 'no'}")
    print("- Existing clones, forks and backups revoked: no")
    print(f"- History inspection: {scope.history_check_status}")
    if scope.history_check_status == "reachable-copy-detected":
        print("  Reachable committed content was detected in the inspected local repository.")
    elif scope.history_check_status == "no-reachable-copy-detected":
        print("  No reachable copy was found in this limited inspection; this is not proof that external or previously distributed copies do not exist.")
    elif scope.history_check_status == "unavailable":
        print("  Git history inspection was unavailable and is not a PASS.")


def render_apply_boundary() -> None:
    print("Removed from the selected managed memory scope.")
    print("Git history and previously distributed copies were not modified.")
