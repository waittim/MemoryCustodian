# MemoryCustodian Generic Agent Instructions

If this project has no `docs/memory/` directory, continue normally. If the directory exists, follow `docs/memory/manifest.md`; if that file is missing, report an incomplete or corrupted setup and do not infer routes.

Always:

- Load `manifest.md` first.
- Load `brief.md` after the manifest.
- Prefer task-specific memory over full history.
- Do not load `archive/` unless asked.
- Do not load `inbox.md` unless compacting or asked.
- Respect tombstones in `do-not-use.md`.
- Load `rules/`, `profiles/`, and `areas/` only when the current task matches them.
- After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose an update.
