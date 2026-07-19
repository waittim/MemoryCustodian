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

### Purge

Use only on explicit request.

- Search active files and `archive/`.
- Remove matching complete semantic units from active files and `archive/`.
- Remove matching topic-bearing soft tombstones and do not add a replacement.
- Keep any operation record generic.

## Preview and broad-match safety

`forget` is dry-run by default. Use `--apply` only after reviewing the full plan. Applying a topic with fewer than four non-whitespace characters, or a plan matching multiple semantic units, also requires `--allow-broad-match`.

Matching is literal and case-insensitive. Delete whole H2 entries or top-level bullet units, never isolated matching lines.

If a match occurs in a plain body or preamble, preview it as `Manual rewrite required`. `--apply` must refuse before the first write until an Agent or user rewrites that content semantically. `--allow-broad-match` does not bypass this blocker.

Treat `do-not-use.md` with tombstone-aware logic rather than as an ordinary deletion target. Hard mode upgrades matching topic-bearing tombstones to one generic guard; purge removes them.

## Soft Tombstone Format

```markdown
## Tombstone: <topic>
Do not reintroduce unless the user explicitly reverses this. Reason: the user asked MemoryCustodian to forget this topic. Mode: soft. Date: YYYY-MM-DD.
```

## Anti-Resurrection Rule

Before compacting or updating memory, check `do-not-use.md`. If an inbox or archive item conflicts with a tombstone, do not re-add it to active memory.

## Sensitive Data

If forgotten content may contain secrets, credentials, personal data, or private identifiers, ask whether the user wants a hard forget or purge. Do not repeat the sensitive value in the tombstone.
