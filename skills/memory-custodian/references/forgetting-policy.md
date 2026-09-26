# Forgetting Policy

Forgetting is a first-class MemoryCustodian operation in package 0.12 / Protocol
0.8. Topic and stable-ID selectors use the same transactional plan, output
envelope, recovery path, and ErasureScope contract.

## Modes

### Soft Forget

Use when the user wants an idea removed from active memory but a guard should remain.

- Preview and remove matching complete semantic units from active memory.
- Add a tombstone to `do-not-use.md`.
- Keep ordinary maintenance history unless the user asks otherwise.

### Hard Forget

Use when the user wants the content gone from memory files.

- Remove matching complete semantic units from active memory.
- Replace matching topic-bearing soft tombstones with one generic redacted guard.
- Never persist the topic in new tombstones or changelog entries.
- Avoid preserving the removed content in summaries.
- Do not describe the result as Git-history erasure or revocation of distributed copies.

### Purge

Use only on explicit request.

- Search active files and `archive/`.
- Remove matching complete semantic units from active files and `archive/`.
- Remove matching topic-bearing soft tombstones and do not add a replacement.
- Keep any operation record generic.
- Do not claim repository-wide or permanent erasure.

## Erasure Boundary

Forgetting controls what remains available to future agents through MemoryCustodian. Soft removes matching active
managed units and may retain a topic-bearing guard. Hard removes matching active units without retaining the topic
in new logs or tombstones. Purge additionally searches the managed `archive/`.

All modes leave Git history and reachable objects unchanged. They do not revoke existing clones, forks, backups,
caches, or external copies, and they do not commit working-tree changes. Preview and apply output MUST be rendered
from the same `ErasureScope` result and state these boundaries explicitly.

## Preview and broad-match safety

`forget` is dry-run by default. Protocol 0.8 previews print a Plan ID; apply requires both `--apply` and the
matching `--confirm-plan`. Any intervening target-file change invalidates the plan. Applying a topic with fewer
than four non-whitespace characters, or a plan matching multiple semantic units, also requires `--allow-broad-match`.

Matching is literal and case-insensitive. Delete whole H2 entries or top-level bullet units, never isolated matching lines.

If a match occurs in a plain body or preamble, preview it as `Manual rewrite required`. `--apply` MUST refuse before the first write until an Agent or user rewrites that content semantically. `--allow-broad-match` does not bypass this blocker.

Treat `do-not-use.md` with tombstone-aware logic rather than as an ordinary deletion target. Hard mode upgrades matching topic-bearing tombstones to one generic guard; purge removes them.

## Soft Tombstone Format

```markdown
## MC-TOMB-YYYYMMDD-8hex — Tombstone: <topic>

Status: active
Scope: project
Evidence:
- user-confirmed

Rejected:
Do not reintroduce unless the user explicitly reverses this request.
```

## Anti-Resurrection Rule

Before compacting or updating memory, check `do-not-use.md`. If an inbox or archive item conflicts with a tombstone, do not re-add it to active memory.

## Sensitive Data

If forgotten content may contain secrets, credentials, personal data, contract parties or identifiers, or private
vendor limits, ask whether the user wants a hard forget or purge. Do not repeat the sensitive value in the
tombstone. Prevention is stronger than cleanup: store a minimal abstract constraint plus an Evidence reference
instead of copying unnecessary sensitive source text into repository memory.

Use `forget --id` when a canonical Entry ID is known; it selects only the unit whose heading owns that ID. A live
relation that references the selected entry is a blocker requiring explicit governance review, not permission to
delete the referencing unit. Canonical reconciliation records are also protected references. A generic hard-mode
`MC-TOMB` deliberately omits topic identity and is treated as an erasure guard rather than a Subject/Facet owner,
so it cannot invalidate later conflict checks. Topic and ID selectors share the same ErasureScope contract.
Optional `--history-check` inspects reachable history in the current local Git repository without changing commits,
refs, the index, remotes, or other clones. `unavailable` is not a PASS. `no-reachable-copy-detected` means only that
this bounded inspection found none; it does not prove the absence of dangling objects, other refs, remotes, forks,
backups, caches, or distributed copies.

`local reset` is scoped to the current machine/current project overlay. Its
Protocol 0.8 apply is transaction-protected and never implies deletion from
other machines or backups.

## Canonical ErasureScope

Every forget, `forget --id`, local reset, and interrupted-forget recovery
result includes `data.erasure_scope` with `erasure_scope_schema_version: 1`.
The required fields are:

```json
{
  "erasure_scope_schema_version": 1,
  "operation_phase": "preview",
  "active_memory": "pending-removal",
  "managed_archive": "not-targeted",
  "local_overlay": "not-applicable",
  "git_worktree_modified": "on-apply",
  "git_history_modified": false,
  "distributed_copies_revoked": false,
  "history_check_status": "not-requested",
  "topic_retained_in_new_records": true
}
```

`operation_phase` is `preview`, `applied`, `no-op`, `recovered-complete`, or
`recovered-rollback`. `active_memory`, `managed_archive`, and `local_overlay`
use `not-targeted`, `no-match`, `pending-removal`, `removed`, `restored`, or
`not-applicable`; `git_worktree_modified` uses `no`, `on-apply`, or `yes`.
`history_check_status` uses `not-requested`, `unavailable`,
`reachable-copy-detected`, or `no-reachable-copy-detected`.

`no-match` means the selector found no managed unit. `pending-removal` means
matching content remains and this operation did not remove it; during
`recovered-rollback`, it can mean every target was still at its journaled base
content before recovery. That value does not mean a transaction remains open or
that deletion is queued. Start a new forget preview and apply if removal is
still intended. Use `restored` only when rollback actually returns content from
a different transaction output to its base content. `git_worktree_modified`
reports shared managed-file changes made by the current command: recovery that
only cleans committed transaction state reports `no`, and local reset always
reports `no` for Git worktree changes.

The scope is a bounded managed-memory statement. `git_history_modified` and
`distributed_copies_revoked` remain false: MemoryCustodian does not rewrite
Git history or revoke clones, forks, backups, caches, or other distributed
copies. `unavailable` is REVIEW, not PASS; bounded
`no-reachable-copy-detected` does not prove that external copies are absent.

Forgetting controls what remains available to future agents through
MemoryCustodian. It is not a guarantee of erasure from Git history or
previously distributed copies.
