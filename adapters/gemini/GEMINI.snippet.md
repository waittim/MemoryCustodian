# Agent Instructions

## MemoryCustodian

This project uses MemoryCustodian for local project memory.

Before substantial work:

1. Read `docs/memory/manifest.md`.
2. Read `docs/memory/brief.md`.
3. Load additional memory files only when the manifest says they are relevant.
4. Do not load `docs/memory/archive/` unless explicitly requested or performing memory maintenance.
5. After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose an update.

Keep this file short. Do not import `docs/memory/` files with `@` directives; Gemini context files are loaded into prompt context, while MemoryCustodian should load project memory through the manifest at task time.
