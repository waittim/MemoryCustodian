# Claude Code Instructions

This repository builds MemoryCustodian: local plain-text memory governance for coding agents.

## MemoryCustodian

Default behavior:

- Read `docs/memory/manifest.md` and `docs/memory/brief.md` before substantial work.
- Load other memory files only when the manifest says they are relevant to the task.
- Keep memory usage minimal.
- Suggest memory updates after decisions, repeated corrections, or rejected approaches.
- Never store sensitive or personal information unless explicitly requested.

Run tests with:

```bash
PYTHONPATH=cli python3 -m unittest discover -s tests
```
