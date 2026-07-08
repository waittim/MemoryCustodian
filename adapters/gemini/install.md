# Gemini Adapter Install

Gemini-style agents can use MemoryCustodian in two complementary ways:

1. Use a thin `GEMINI.md` project context file to point at `docs/memory/`.
2. Install or link the `memory-custodian` skill so the agent can use the full protocol for memory maintenance tasks.

## Install The Skill

From this repository, install MemoryCustodian into Gemini's personal skills directory:

```bash
./install.sh gemini
```

This creates a symlink at `${GEMINI_HOME:-$HOME/.gemini}/skills/memory-custodian` pointing to `skills/memory-custodian`.

For local development with Gemini CLI skill management, you can also link the skill directly:

```bash
gemini skills link ./skills/memory-custodian
```

## Bootstrap A Project

Use the CLI if it is available:

```bash
memory-custodian init --project-root <project> --with-gemini
```

Or add the contents of `GEMINI.snippet.md` to the target project's `GEMINI.md`.

Keep `GEMINI.md` as an entry point. Do not import `docs/memory/` files from `GEMINI.md`; store durable memory in `docs/memory/` and let the manifest control task-specific loading.
