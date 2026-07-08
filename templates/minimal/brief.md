# Project Brief

This project uses MemoryCustodian to maintain local, plain-text project memory.

Current status:
- Minimal memory protocol is enabled.
- Durable memory lives in `docs/memory/`.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` should stay short and only point to this memory folder.

Default behavior:
- Load `manifest.md`.
- Load `brief.md`.
- Load additional memory files only when relevant.
