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
- keep platform entry files such as `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` short

## Hard Gate

In a project that contains MemoryCustodian memory, do not start substantial planning, implementation, debugging, or review until startup loading is complete:

1. Read `manifest.md` if present. If the memory directory exists but the file does not, stop as described below.
2. Read `brief.md` before substantial work.
3. Identify the task type.
4. Load only files allowed by the manifest and matched by the current task.
5. Respect `do-not-use.md` and tombstones before proposing plans or implementations.

If no memory directory exists, continue normally and offer initialization only when useful. If the memory directory exists but `manifest.md` is missing, stop memory loading and report an incomplete or corrupted setup. Do not infer routes; restore the manifest, migrate, or carefully reinitialize the project first.

## Core Workflow

1. Locate memory at `docs/memory/manifest.md`, or another project-declared memory directory under `docs/`.
2. Read `manifest.md`; it is the sole authority for runtime task-to-file routing.
3. Read `brief.md` before substantial work.
4. Identify the task type.
5. Use the manifest optional module index to discover enabled `rules/`, `profiles/`, and `areas/` files.
6. Load only files allowed by the manifest and matched by the current task.
7. Respect `do-not-use.md` and tombstones before proposing plans or implementations.
8. Never load `archive/` unless the user explicitly asks or the task is archive maintenance.
9. Do not load `inbox.md` unless compacting, auditing unsorted memory, or asked by the user.
10. If `brief.md` is still a generated scaffold, curate it from authoritative project files before relying on it.
11. After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose a concise update.

## Memory Files

- `manifest.md`: loading protocol, optional module index, file roles, and context budgets.
- `brief.md`: short current project summary; this is the default file.
- `decisions.md`: confirmed project and architecture decisions.
- `constraints.md`: hard requirements and limits.
- `do-not-use.md`: rejected options, failure paths, and tombstones.
- `inbox.md`: unprocessed memory candidates.
- `preferences.md`: optional user and project preferences.
- `changelog.md`: optional memory maintenance history, not product release notes or the project `CHANGELOG.md`.
- `rules/`: optional task-specific rules.
- `profiles/`: optional workflow-specific rules.
- `areas/`: optional area-specific memory.
- `archive/`: optional old material loaded only on request.

## Task Loading

Classify the task as general continuation, planning, implementation, artifact work, preferences, history, maintenance, or another category defined by the project manifest. Then follow the current manifest exactly and use the smallest routed set that can answer the task. Any routes in generated templates or examples are defaults only; they never override a customized project manifest.

## Writing Memory

Write durable memory only when it is project-level and likely to matter later.

- Classify scope before content type. When the manifest routes matched `areas/*.md`, put subsystem-specific choices and invariants there; reserve root `decisions.md` for cross-cutting choices.
- Update, merge, or mark an existing entry superseded when a new choice changes it; do not append a contradictory duplicate.
- Keep active invariants reachable from normal task loading. Promote them to `brief.md`, `constraints.md`, or a matched area before archiving history.
- Confirmed cross-cutting choices go to `decisions.md`.
- Hard limits go to `constraints.md`.
- Style or workflow preferences go to `preferences.md`.
- Rejected options and deletion guards go to `do-not-use.md`.
- Task rules go to `rules/`.
- Workflow rules go to `profiles/`.
- Area-specific context goes to `areas/`.
- Unsorted or uncertain notes go to `inbox.md`.

Keep each decision entry at or below 120 tokens, including its title, `Decision`, and `Reason`. Use one or two sentences for the decision and one sentence for the reason. Move implementation detail, examples, and long implications into constraints, matched area context, or source documentation. Never truncate mechanically; rewrite semantically. Use `--allow-long` only when splitting would lose essential decision semantics.

Keep `brief.md` about the project, not MemoryCustodian. Refresh it after initialization and when the project purpose, system shape, or current direction materially changes.

For sensitive, personal, credential-like, private, or machine-specific information, ask before writing. Do not commit workstation paths as shared project preferences without confirmation. When unsure whether a note is durable, propose the update instead of writing it.

After writing, check the target budget. At 80% or above, consolidate or split by area before adding more entries.

## Compaction Safety

Inbox compaction is a two-stage workflow. The CLI reports candidates and may remove only exact duplicates or exact tombstone matches; it never promotes an entry to a semantic destination. The Agent reviews each remaining candidate's scope, type, confidence, and overlap, then edits the appropriate Markdown or calls `add`. Run `check` afterward.

Treat decision compaction as semantic maintenance, not chronological trimming. Before applying age-based archival:

1. Shorten decision entries over 120 tokens without losing the choice or reason.
2. Merge duplicates and mark superseded decisions.
3. Move scoped knowledge to matched areas.
4. Retain every active invariant in `brief.md`, `constraints.md`, root decisions, or a matched area.
5. Review the CLI dry run, then use explicit archival confirmation only if the remaining archive candidates are historical.

## Forgetting

When the user asks to forget something:

1. Preview the complete semantic-unit plan before writing.
2. Apply only after explicit `--apply`; use `--allow-broad-match` for short topics or multi-unit plans.
3. Remove whole H2 entries or top-level bullets, never matching lines alone.
4. If a body or preamble matches, require a semantic manual rewrite and refuse apply until it is resolved.
5. Add a topic-bearing tombstone only for soft mode; hard replaces prior topic-bearing tombstones with one generic guard, while purge removes them.
6. Do not reintroduce the forgotten content during compaction.

## References

Load these only when needed:

- `references/memory-file-protocol.md`: file schema, budgets, and loading levels.
- `references/manifest-policy.md`: manifest routing and loading policy.
- `references/platform-adapters.md`: Codex, Claude Code, Gemini, and generic agent entry patterns.
- `references/compaction-policy.md`: how to reduce inbox and long files safely.
- `references/quality-audit.md`: how to audit usefulness, routing, scope, freshness, and portability.
- `references/forgetting-policy.md`: soft forget, hard forget, purge, and tombstones.
- `references/examples.md`: example memory files and context packs.

## CLI

If the project has the CLI installed, prefer deterministic commands for routine operations:

```bash
memory-custodian status
memory-custodian read --task planning
memory-custodian add "..." --type decision
memory-custodian add "..." --type decision --area sync --reason "..."
memory-custodian add "..." --type decision --allow-long
memory-custodian enable rules/output
memory-custodian compact
memory-custodian compact --apply  # exact mechanical inbox cleanup only
memory-custodian compact --target decisions.md
memory-custodian compact --target decisions.md --apply --archive-oldest
memory-custodian forget "topic" --mode soft
memory-custodian forget "topic" --mode soft --apply
memory-custodian check
memory-custodian migrate --apply
```

If the console script is unavailable but this skill came from an installed plugin or source checkout, use the bundled helper from the plugin root:

```bash
scripts/memory-custodian status
scripts/memory-custodian read --task planning
```

If the CLI is unavailable, edit the markdown files directly using the same protocol.
