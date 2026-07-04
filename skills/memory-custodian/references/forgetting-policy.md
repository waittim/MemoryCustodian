# Forgetting Policy

Forgetting is a first-class MemoryCustodian operation.

## Modes

### Soft Forget

Use when the user wants an idea removed from active memory but a guard should remain.

- Remove matching content from common files.
- Add a tombstone to `do-not-use.md`.
- Keep ordinary maintenance history unless the user asks otherwise.

### Hard Forget

Use when the user wants the content gone from memory files.

- Remove matching content from all memory markdown files that are not the tombstone destination.
- Add only a minimal tombstone topic to `do-not-use.md` if needed.
- Avoid preserving the removed content in summaries.

### Purge

Use only on explicit request.

- Search active files and `archive/`.
- Remove matching raw notes and references.
- Leave only a minimal tombstone topic if a guard is required.

## Tombstone Format

```markdown
## Tombstone: <topic>
Do not reintroduce unless the user explicitly reverses this. Reason: the user asked MemoryCustodian to forget this topic. Mode: soft | hard | purge. Date: YYYY-MM-DD.
```

## Anti-Resurrection Rule

Before compacting or updating memory, check `do-not-use.md`. If an inbox or archive item conflicts with a tombstone, do not re-add it to active memory.

## Sensitive Data

If forgotten content may contain secrets, credentials, personal data, or private identifiers, ask whether the user wants a hard forget or purge. Do not repeat the sensitive value in the tombstone.
