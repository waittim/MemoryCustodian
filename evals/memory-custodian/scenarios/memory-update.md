# Memory Update

## Purpose
Verify that durable project decisions are recorded in the right memory file without bloating platform entry files.

## Setup
- A project already uses MemoryCustodian under `docs/memory/`.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` are thin bootstraps.
- The user makes a durable architecture decision during implementation.

## Prompt
The user says: "Let's make optional workflow profiles non-default; agents should only load them when the manifest says they match."

## Required Observations
- Agent classifies the statement as a durable project decision.
- Agent updates or proposes updating `docs/memory/decisions.md`.
- Agent keeps `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` as pointers rather than storage.
- Agent mentions the memory update concisely in its handoff.

## Forbidden Outcomes
- Agent writes the decision only into chat.
- Agent copies the decision into platform entry files as long-term memory.
- Agent creates a default profile file just because workflow profiles were discussed.

## Passing Criteria
Pass when the decision lands in `decisions.md` or is explicitly proposed there, with no platform entry bloat.
