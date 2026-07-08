# Project Brief

Purpose:
MemoryCustodian is a local-first, pure-text project memory skill and CLI for coding agents.
It reduces repeated project explanation across threads and chats by keeping durable context in repository-local Markdown files.
It narrows the gap between developers' context advantage and agents' accessible context so development loops and loop engineering stay smoother.

Current direction:
- Build a reusable skill under `skills/memory-custodian/`.
- Package the skill as a Codex plugin with repo-local marketplace support and a bundled CLI wrapper.
- Store managed project memory in `docs/memory/` by default.
- Provide Codex, Claude Code, Gemini, and generic adapter snippets.
- Provide a lightweight Python CLI for init, read, add, compact, forget, enable, migrate, check, and status.
- Keep default initialization minimal: manifest, brief, decisions, constraints, do-not-use, and inbox.
- Keep optional preferences, changelog, rules, profiles, areas, and archive disabled until needed.
- Keep context packs small and manifest-driven; default to `brief.md` only.
