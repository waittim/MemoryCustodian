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
- Provide a lightweight Python CLI for deterministic routing, local overlays, ID operations, conflict/quality checks, and memory mutation.
- Keep default initialization minimal: six task-memory files plus the non-routed `subjects.md` identity registry.
- Keep optional preferences, changelog, rules, profiles, areas, and archive disabled until needed.
- Keep context packs small and manifest-driven; substantial work uses `brief.md` plus root constraints and explicit scope.
- Keep memory useful through real project briefs, concise scope-first decisions, and semantic review before decision archival.
