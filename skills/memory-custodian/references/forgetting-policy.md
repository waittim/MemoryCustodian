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
- Add only a generic redacted guard; never persist the topic in tombstones or changelog entries.
- Avoid preserving the removed content in summaries.

### Purge

Use only on explicit request.

- Search active files and `archive/`.
- Remove matching complete semantic units from active files and `archive/`.
- Do not add a topic-bearing tombstone; keep any operation record generic.

## Preview and broad-match safety

`forget` is dry-run by default. Use `--apply` only after reviewing the full plan. Applying a topic with fewer than four non-whitespace characters, or a plan matching multiple semantic units, also requires `--allow-broad-match`.

Matching is literal and case-insensitive. Delete whole H2 entries or top-level bullet units, never isolated matching lines.

## Soft Tombstone Format

```markdown
## Tombstone: <topic>
Do not reintroduce unless the user explicitly reverses this. Reason: the user asked MemoryCustodian to forget this topic. Mode: soft. Date: YYYY-MM-DD.
```

## Anti-Resurrection Rule

Before compacting or updating memory, check `do-not-use.md`. If an inbox or archive item conflicts with a tombstone, do not re-add it to active memory.

## Sensitive Data

If forgotten content may contain secrets, credentials, personal data, or private identifiers, ask whether the user wants a hard forget or purge. Do not repeat the sensitive value in the tombstone.
