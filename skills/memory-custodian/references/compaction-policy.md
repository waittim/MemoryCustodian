# Compaction Policy

Compaction reduces context bloat while preserving durable project memory.

## When To Compact

Compact when:

- `inbox.md` has more than 30 items.
- `brief.md` exceeds its budget.
- Any active memory file exceeds its context budget.
- The same fact appears in multiple files.
- A decision or constraint has stabilized.
- A user asks to summarize or tidy memory.

## Compaction Inputs

Usually read:

- `brief.md`
- `inbox.md`
- relevant destination files such as `decisions.md`, `constraints.md`, `preferences.md`, and `do-not-use.md`

Do not read `archive/` unless the user asks.

## Destination Rules

- Confirmed architecture choices -> `decisions.md`
- Hard requirements -> `constraints.md`
- User style or workflow preferences -> `preferences.md`
- Rejected paths and tombstones -> `do-not-use.md`
- Task-specific rules -> `rules/*.md`
- Workflow-specific rules -> `profiles/*.md`
- Current one-screen summary -> `brief.md`
- Unclear or temporary notes -> keep in `inbox.md`

## Safety Rules

- Do not erase uncertain information silently.
- Do not resurrect topics listed in `do-not-use.md`.
- Preserve the decision, not the full conversation.
- Prefer short bullets over narrative history.
- Keep tombstones active; do not archive `do-not-use.md` entries merely to meet a budget.
- Archive only complete old entries, and only when the active file remains coherent without them.
- Record a short maintenance note in `changelog.md` if it is enabled.

## CLI Behavior

The CLI can deduplicate and classify obvious inbox bullets, but semantic compaction should be reviewed by an agent or user.

Use `memory-custodian compact` for an inbox dry run and `memory-custodian compact --apply` for deterministic inbox changes.

For an over-budget active file, use `memory-custodian compact --target decisions.md` first. With `--target`, the CLI reports the current budget state and applies only conservative deterministic changes: exact duplicate bullet removal for simple bullet files, or older complete H2 entry archival for supported history-like files such as `decisions.md` and `changelog.md`. Use `--apply` only after reviewing the plan.
