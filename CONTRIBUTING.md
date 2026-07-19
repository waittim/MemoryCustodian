# Contributing

MemoryCustodian is a local-first, pure-text project memory skill and CLI for coding agents. Keep changes small, inspectable, and friendly to source control.

## Before You Start

- Read `AGENTS.md`.
- Read `docs/memory/manifest.md`, then `docs/memory/brief.md`.
- Load additional memory files only when the manifest says they are relevant.
- Do not load `docs/memory/archive/` unless explicitly requested or performing memory maintenance.
- After meaningful decisions or repeated corrections, update the appropriate memory file or propose an update.

## Repository Layout

```text
MemoryCustodian/
  .codex-plugin/plugin.json        # Codex plugin manifest
  .claude-plugin/plugin.json       # Claude plugin metadata
  .claude-plugin/marketplace.json  # Claude local development marketplace metadata
  .agents/plugins/marketplace.json # Repo-local plugin marketplace for testing
  GEMINI.md                        # Thin Gemini context entry for this repository
  hooks/                           # Lightweight session-start bootstrap for plugin hosts
  skills/memory-custodian/         # Reusable agent skill
  adapters/                        # Codex, Claude Code, Gemini, and generic entry snippets
  cli/memory_custodian/            # Python CLI implementation
  bin/memory-custodian             # Claude plugin PATH wrapper
  scripts/memory-custodian         # Plugin-safe CLI wrapper
  scripts/package-codex-plugin.py  # Deterministic Codex plugin archive builder
  evals/memory-custodian/          # Static skill contract scenarios
  templates/minimal/               # Core protocol templates
  templates/extended/              # Optional memory module scaffolding
  docs/memory/                     # Dogfood memory for this repository
  tests/                           # Focused stdlib unittest suite
```

## Development Checks

Run the unit tests:

```bash
PYTHONPATH=cli python3 -m unittest discover -s tests
```

Run the static skill contract checks. They validate required instructions, scenario structure, required observations, forbidden outcomes, and contractual wording; they do not execute an Agent or model runtime:

```bash
PYTHONPATH=cli python3 scripts/check-skill-evals.py
```

Check the current memory set:

```bash
PYTHONPATH=cli python3 -m memory_custodian.main check
```

Check whitespace before committing:

```bash
git diff --check
```

## Packaging

Build a deterministic Codex plugin archive:

```bash
python3 scripts/package-codex-plugin.py --allow-dirty --output /tmp/memory-custodian.zip
```

Use `--allow-dirty` only for local verification. Release packaging should happen from an intentional tree state.

## Development Notes

- The CLI uses Python stdlib only.
- Keep skill instructions concise; put detailed policy in `skills/memory-custodian/references/`.
- Keep platform files thin. `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` should point agents at MemoryCustodian rather than importing all memory content.
- Custom memory directories, if explicitly configured, must still live under `docs/`.
