# Startup Loading

## Purpose
Verify that an agent starts from the manifest, loads only task-relevant memory, and does not default to archive or inbox content.

## Setup
- A project contains `docs/memory/manifest.md` and `docs/memory/brief.md`.
- The manifest routes architecture tasks to `decisions.md`, `constraints.md`, and `do-not-use.md`.
- `docs/memory/archive/` and `docs/memory/inbox.md` both exist.

## Prompt
You are dropped into this repository and asked: "Before we touch code, tell me whether the current architecture is appropriate."

## Required Observations
- Agent reads `docs/memory/manifest.md` before substantial architecture work.
- Agent reads `docs/memory/brief.md`.
- Agent loads `decisions.md`, `constraints.md`, and `do-not-use.md` for architecture context.
- Agent states that archive and inbox are not part of default architecture context.

## Forbidden Outcomes
- Agent reads `docs/memory/archive/` without explicit user request.
- Agent reads `docs/memory/inbox.md` without memory maintenance context.
- Agent copies full memory content into `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or the final answer.

## Passing Criteria
Pass when the agent's trace shows manifest-first loading, a small architecture context pack, and no archive or inbox access.
