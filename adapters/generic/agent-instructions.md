# MemoryCustodian Generic Agent Instructions

If this project contains `docs/memory/manifest.md`, follow it.

Always:

- Load `manifest.md` first.
- Load `brief.md` after the manifest.
- Prefer task-specific memory over full history.
- Do not load `archive/` unless asked.
- Do not load `inbox.md` unless compacting or asked.
- Respect tombstones in `do-not-use.md`.
- Load `rules/`, `profiles/`, and `areas/` only when the current task matches them.
- Update memory files only when the user agrees or the task clearly requires it.
