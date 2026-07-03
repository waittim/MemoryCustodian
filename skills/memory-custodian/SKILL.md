---
name: memory-custodian
description: Use when a project contains docs/memory/, or when the user asks to remember, retrieve, update, compact, forget, or audit project memory. MemoryCustodian manages local plain-text project memory with minimal context loading.
---

# MemoryCustodian

MemoryCustodian stores durable project memory as local, human-readable Markdown files under `docs/memory/`.

Use it to:
- load the minimum relevant project memory for the current task
- update project memory after meaningful decisions
- compact unprocessed memory candidates
- forget or tombstone memory the user no longer wants used
- keep platform entry files such as `AGENTS.md` and `CLAUDE.md` short

## Core Workflow

1. Locate memory: prefer `docs/memory/manifest.md`; fall back to `.memory/manifest.md` only if the project explicitly chose it.
2. Read `manifest.md` if present.
3. Read `brief.md` before substantial work.
4. Identify the task type.
5. Use the manifest optional module index to discover enabled `rules/`, `profiles/`, and `areas/` files.
6. Load only files allowed by the manifest and matched by the current task.
7. Respect `do-not-use.md` and tombstones before proposing plans or implementations.
8. Never load `archive/` unless the user explicitly asks or the task is archive maintenance.
9. Do not load `inbox.md` unless compacting, auditing unsorted memory, or asked by the user.
10. After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose a concise update.

## Memory Files

- `manifest.md`: loading protocol, optional module index, file roles, and context budgets.
- `brief.md`: short current project summary; this is the default file.
- `decisions.md`: confirmed project and architecture decisions.
- `constraints.md`: hard requirements and limits.
- `do-not-use.md`: rejected options, failure paths, and tombstones.
- `inbox.md`: unprocessed memory candidates.
- `preferences.md`: optional user and project preferences.
- `changelog.md`: optional memory maintenance history.
- `rules/`: optional task-specific rules.
- `profiles/`: optional workflow-specific rules.
- `areas/`: optional area-specific memory.
- `archive/`: optional old material loaded only on request.

## Task Loading

Use the smallest set that can answer the task:

- General continuation: `brief.md`
- Architecture or planning: `brief.md`, `decisions.md`, `constraints.md`, `do-not-use.md`
- Implementation or debugging: `brief.md`, `constraints.md`, `do-not-use.md`, and `preferences.md` if present
- User-facing artifacts: `brief.md`, `do-not-use.md`, `rules/output.md` if present, and `preferences.md` if present
- Preferences: `brief.md`, `preferences.md` if present
- Memory status or history: `brief.md`, `decisions.md`, and `changelog.md` if present
- Compaction: `brief.md`, `inbox.md`, `do-not-use.md`, and files that may receive merged content
- Forgetting: search relevant memory files, then update `do-not-use.md`

## Writing Memory

Write durable memory only when it is project-level and likely to matter later.

- Confirmed choices go to `decisions.md`.
- Hard limits go to `constraints.md`.
- Style or workflow preferences go to `preferences.md`.
- Rejected options and deletion guards go to `do-not-use.md`.
- Task rules go to `rules/`.
- Workflow rules go to `profiles/`.
- Area-specific context goes to `areas/`.
- Unsorted or uncertain notes go to `inbox.md`.

For sensitive, personal, credential-like, or private information, ask before writing. When unsure whether a note is durable, propose the update instead of writing it.

## Forgetting

When the user asks to forget something:

1. Locate matching memory in common memory files.
2. Remove or rewrite the matching entry.
3. Add a tombstone to `do-not-use.md` when the topic may otherwise reappear.
4. Do not reintroduce the forgotten content during compaction.
5. For hard forget or purge requests, avoid preserving the removed content in summaries.

## References

Load these only when needed:

- `references/memory-file-protocol.md`: file schema, budgets, and loading levels.
- `references/manifest-policy.md`: manifest routing and loading policy.
- `references/platform-adapters.md`: Codex, Claude Code, and generic agent entry patterns.
- `references/compaction-policy.md`: how to reduce inbox and long files safely.
- `references/forgetting-policy.md`: soft forget, hard forget, purge, and tombstones.
- `references/examples.md`: example memory files and context packs.

## CLI

If the project has the CLI installed, prefer deterministic commands for routine operations:

```bash
memory-custodian status
memory-custodian read --task planning
memory-custodian add "..." --type decision
memory-custodian enable rules/output
memory-custodian compact --apply
memory-custodian forget "topic" --mode soft
memory-custodian check
```

If the CLI is unavailable, edit the markdown files directly using the same protocol.
