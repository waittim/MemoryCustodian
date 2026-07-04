# Session Bootstrap

## Purpose
Verify that installed plugin startup context nudges agents toward MemoryCustodian loading without injecting the full skill or large project memory.

## Setup
- MemoryCustodian is installed as a plugin.
- The target project may or may not contain `docs/memory/manifest.md`.
- The session-start hook runs before the first agent response.

## Prompt
The user opens a new session in a MemoryCustodian-managed project and asks: "Can you start by checking what matters in this repo?"

## Required Observations
- Startup context tells the agent to read the manifest and brief before substantial work when project memory exists.
- Startup context states that archive and inbox are not default loads.
- Startup context points to the memory-custodian skill or CLI for maintenance tasks.
- Startup context is concise and does not embed the full `SKILL.md` body.

## Forbidden Outcomes
- The hook injects the entire MemoryCustodian skill content.
- The hook injects project-specific memory file contents.
- The hook tells agents to load `archive/` or `inbox.md` by default.
- The hook requires network access.

## Passing Criteria
Pass when a clean session receives only the lightweight bootstrap and the agent follows manifest-first loading before substantial work.
