# Platform Adapters

MemoryCustodian separates the memory protocol from platform-specific entry points.

```text
MemoryCustodian Core Protocol
  -> Generic Skill Instructions
  -> Platform Adapter
  -> Codex / Claude Code / Cursor / Gemini / Others
```

## Codex

Codex projects should keep `AGENTS.md` short and point to `docs/memory/`.

Recommended behavior:

1. Read `docs/memory/manifest.md` before substantial work.
2. Read `docs/memory/brief.md`.
3. Read task-specific files only when the manifest says they are relevant.
4. Do not load `inbox.md` or `archive/` unless asked or maintaining memory.
5. After meaningful decisions, repeated corrections, or rejected approaches, update the appropriate memory file or propose an update.

Use `adapters/codex/AGENTS.snippet.md`.

## Claude Code

Claude Code projects should keep `CLAUDE.md` short and point to `docs/memory/`.

Recommended behavior:

- Read `manifest.md` and `brief.md` before substantial work.
- Load other files only when the manifest says they are relevant.
- Keep memory usage minimal.
- Use commands for status, compact, and forget where available.

Use `adapters/claude-code/CLAUDE.snippet.md` and optional command files under `adapters/claude-code/commands/`.

## Gemini

Gemini-style agents should keep `GEMINI.md` short and point to `docs/memory/`.

Recommended behavior:

- Read `manifest.md` and `brief.md` before substantial work.
- Load other files only when the manifest says they are relevant.
- Do not import `docs/memory/` files from `GEMINI.md`; Gemini context imports are loaded into prompt context.
- Install or link `skills/memory-custodian/` as a Gemini Agent Skill when available.

Use `adapters/gemini/GEMINI.snippet.md`.

## Generic Agents

Generic agents should follow `docs/memory/manifest.md` if present. If no manifest exists, load `brief.md` first and then only task-relevant files.

Use `adapters/generic/agent-instructions.md`.

## Adapter Rule

Adapters should be entry points, not memory stores. Do not copy full project memory into `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or equivalent instruction files.
