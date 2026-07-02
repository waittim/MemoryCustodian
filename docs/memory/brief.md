# Project Brief

Purpose:
MemoryCustodian is a local-first, pure-text project memory skill and CLI for coding agents.

Current direction:
- Build a reusable skill under `skills/memory-custodian/`.
- Store managed project memory in `docs/memory/` by default.
- Provide Codex, Claude Code, and generic adapter snippets.
- Provide a lightweight Python CLI for init, read, add, compact, forget, enable, check, and status.
- Keep default initialization minimal: manifest, brief, decisions, constraints, do-not-use, and inbox.
- Keep optional preferences, changelog, rules, profiles, areas, and archive disabled until needed.
- Keep context packs small and manifest-driven; default to `brief.md` only.
