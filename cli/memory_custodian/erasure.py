"""Structured forgetting scope with explicit non-erasure boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ErasureScope:
    active_memory: bool
    managed_archive: bool
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
) -> ErasureScope:
    return ErasureScope(
        active_memory=active_matches,
        managed_archive=archive_matches,
        local_overlay="not-applicable",
        git_worktree_modified="on-apply" if has_mutations else "no",
        git_history_modified=False,
        distributed_copies_revoked=False,
        history_check_status=history_check_status,
        topic_retained_in_new_records=mode == "soft",
    )


def render_scope(scope: ErasureScope) -> None:
    yes_no = lambda value: "yes" if value else "no"
    print("Removal scope:")
    print(f"- Active managed memory: {yes_no(scope.active_memory)}")
    print(f"- Managed archive: {yes_no(scope.managed_archive)}")
    print(
        "- New tombstones/logs retain topic: "
        + yes_no(scope.topic_retained_in_new_records)
    )
    print(f"- Local overlay: {scope.local_overlay}")
    print(f"- Git worktree modified: {scope.git_worktree_modified}")
    print(f"- Git history modified: {yes_no(scope.git_history_modified)}")
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
