# NightNotes MemoryCustodian Demo

This fixture demonstrates how a new coding-agent session recovers project
decisions without receiving them in the prompt. NightNotes is intentionally a
minimal project skeleton: its in-memory note store does not yet persist notes,
and the acceptance test documents the missing behavior.

[Watch the published demo](https://www.youtube.com/watch?v=mYKzzATlOPw).

## Confirm the Starting Point

From the MemoryCustodian repository root:

```bash
cd examples/nightnotes-video-demo
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

The persistence test should fail because a note added to one `NoteStore`
instance is not available to a later instance. This expected failure is the
implementation task, not a broken demo setup.

## Inspect the Planning Context

From the MemoryCustodian repository root:

```bash
scripts/memory-custodian read \
  --project-root examples/nightnotes-video-demo \
  --task planning
```

Expected memory:

- Use human-readable local JSON.
- Work without network access.
- Use only the Python standard library for routine operation.
- Keep existing note files human-readable.
- Do not introduce SQLite for the current session store.

## Inspect the Semantic-Review Boundary

```bash
scripts/memory-custodian compact \
  --project-root examples/nightnotes-video-demo
```

On Windows, install the console command first and replace
`scripts/memory-custodian` with `memory-custodian`.

The encryption candidate should remain for Agent review. The CLI should not
infer a semantic destination for it.

## Codex Test

Open this directory as a new Codex project with no prior conversation context,
then run:

```text
Plan how to implement persistent session state.

Before proposing changes, use the repository's project memory. Explain which
existing decisions, constraints, and rejected approaches influenced your plan.

Do not modify any files.
```

Success means the plan selects local JSON, preserves offline operation and
standard-library-only routine behavior, respects the rejected SQLite approach,
and modifies no files.

## Fixture Layout

- `nightnotes/`: Minimal in-memory note store and CLI skeleton.
- `tests/`: Acceptance test for persistence across store instances.
- `docs/memory/`: Curated MemoryCustodian project memory.
- `AGENTS.md`: Thin agent entry point for the memory protocol.
