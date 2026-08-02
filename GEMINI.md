@./skills/memory-custodian/SKILL.md

# Agent Instructions

This repository builds MemoryCustodian: a local-first, pure-text project memory skill and CLI for coding agents.

## MemoryCustodian

Before substantial work in this repository:

1. Read `docs/memory/manifest.md` and `docs/memory/brief.md`.
2. Choose a canonical task and supply touched/planned paths or an explicit area.
3. Use strict routing before substantial work; stop on incomplete/invalid routing or unresolved conflicts.
4. Do not infer areas/profiles from prose or load archive/inbox outside their explicit maintenance boundaries.
5. After meaningful decisions or repeated corrections, update evidence-backed memory or propose an update.

Keep this file short. Do not import `docs/memory/` files here; Gemini context files are loaded into prompt context, while MemoryCustodian should load project memory through the manifest at task time.

## Development

- The CLI uses Python stdlib only.
- Run tests with `PYTHONPATH=cli python3 -m unittest discover -s tests`.
- Keep Skill instructions concise; put detailed policy in `skills/memory-custodian/references/`.
