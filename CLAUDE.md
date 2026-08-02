# Claude Code Instructions

This repository builds MemoryCustodian: local plain-text memory governance for coding agents.

## MemoryCustodian

Default behavior:

- Read `docs/memory/manifest.md` and `docs/memory/brief.md`, choose a canonical task, and expose touched/planned paths or an explicit area.
- Use strict routing and stop substantial work on incomplete/invalid routing or unresolved conflicts.
- Never infer area/profile routes from prose or load archive/inbox outside explicit maintenance.
- Keep memory usage minimal.
- Suggest memory updates after decisions, repeated corrections, or rejected approaches.
- Never store sensitive or personal information unless explicitly requested.

Run tests with:

```bash
PYTHONPATH=cli python3 -m unittest discover -s tests
```
