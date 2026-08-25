# Forgetting Policy

Forgetting is a first-class MemoryCustodian operation.

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
caches, or external copies, and they do not commit working-tree changes. Preview and apply output must be rendered
from the same `ErasureScope` result and state these boundaries explicitly.

## Preview and broad-match safety

`forget` is dry-run by default. Protocol 0.6 previews print a Plan ID; apply requires both `--apply` and the
matching `--confirm-plan`. Any intervening target-file change invalidates the plan. Applying a topic with fewer
than four non-whitespace characters, or a plan matching multiple semantic units, also requires `--allow-broad-match`.

Matching is literal and case-insensitive. Delete whole H2 entries or top-level bullet units, never isolated matching lines.

If a match occurs in a plain body or preamble, preview it as `Manual rewrite required`. `--apply` must refuse before the first write until an Agent or user rewrites that content semantically. `--allow-broad-match` does not bypass this blocker.

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
