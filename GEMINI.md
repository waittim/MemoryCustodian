@./skills/memory-custodian/SKILL.md

# Agent Instructions

This repository builds MemoryCustodian: a local-first, pure-text project memory skill and CLI for coding agents.

## MemoryCustodian

Before substantial work in this repository:

1. Read `docs/memory/manifest.md`.
2. Read `docs/memory/brief.md`.
3. Load additional memory files only when the manifest says they are relevant.
4. Do not load `docs/memory/archive/` unless explicitly requested or performing memory maintenance.
5. After meaningful decisions or repeated corrections, update the appropriate memory file or propose an update.

Keep this file short. Do not import `docs/memory/` files here; Gemini context files are loaded into prompt context, while MemoryCustodian should load project memory through the manifest at task time.

## Development

- The CLI uses Python stdlib only.
- Run tests with `PYTHONPATH=cli python3 -m unittest discover -s tests`.
- Keep Skill instructions concise; put detailed policy in `skills/memory-custodian/references/`.
