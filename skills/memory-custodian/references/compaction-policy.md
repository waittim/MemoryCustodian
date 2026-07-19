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

Follow the project manifest's memory-maintenance route, then read only the candidates and potential destinations needed for review.

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
- Shorten entries over 120 tokens semantically before archiving other decisions; never truncate mechanically.
- Prefer short bullets over narrative history.
- Keep tombstones active; do not archive `do-not-use.md` entries merely to meet a budget.
- Before archiving decisions, merge superseded entries and move subsystem-specific knowledge to matched `areas/*.md`.
- Preserve every active invariant in normal task-loading paths; archive only historical rationale or inactive entries.
- Archive only complete old entries, and only when the active file remains coherent and sufficient without them.
- Record a short maintenance note in `changelog.md` if it is enabled.

## CLI Behavior

The CLI must not classify inbox entries by keywords or infer semantic destinations. It may report budgets and candidates, remove exact duplicate bullets, and filter exact tombstone matches. All other candidates remain in the inbox until an Agent or user reviews their scope, type, confidence, and overlap with existing memory.

Use `memory-custodian compact` to generate the candidate report. After review, edit the destination Markdown directly or call `add`, then run `check`. Use `memory-custodian compact --apply` only to apply the exact mechanical inbox cleanup shown in the preview; it does not promote candidates or remove them merely because they were reported.

For an over-budget active file, use `memory-custodian compact --target decisions.md` first. With `--target`, the CLI reports the current budget state and applies only conservative deterministic changes: exact duplicate bullet removal for simple bullet files, or older complete H2 entry archival for supported history-like files such as `decisions.md` and `changelog.md`.

Decision archival has an explicit semantic gate. First shorten long entries, consolidate, supersede, and relocate scoped knowledge; then review the dry run. The CLI blocks age-based archival while kept decisions remain over the per-entry guide. Use `--apply --archive-oldest` only when the proposed oldest entries contain no active invariant that would become unreachable. Changelog archival does not require this extra confirmation.
