# MemoryCustodian

Repo-native memory governance for agents.

MemoryCustodian is a local-first, pure-text project memory protocol, skill, and CLI. It lets coding agents share durable project context through human-readable Markdown files while keeping each task's loaded context small.

Memory can grow; context must stay small.

## What It Provides

- A project memory file protocol under `docs/memory/`
- A reusable Codex-compatible skill at `skills/memory-custodian/SKILL.md`
- Platform entry snippets for Codex, Claude Code, and generic agents
- A small Python CLI for deterministic memory operations
- Minimal and extended templates for project memory files that can be reviewed, diffed, committed, and rolled back

## Non-Goals

MemoryCustodian does not provide:

- RAG retrieval
- embedding-based search
- vector database storage
- cloud-hosted memory
- opaque platform-specific memory stores
- chat log archiving
- a background daemon
- a default Git workflow
- automatic full-context loading

## Repository Layout

```text
MemoryCustodian/
  skills/memory-custodian/        # Reusable agent skill
  adapters/                       # Codex, Claude Code, and generic entry snippets
  cli/memory_custodian/           # Python CLI implementation
  templates/minimal/              # Core protocol templates
  templates/extended/             # Optional memory module templates
  docs/memory/                    # Dogfood memory for this repository
  tests/                          # Focused stdlib unittest suite
```

## Quick Start

Run the CLI from a source checkout by setting `PYTHONPATH`:

```bash
PYTHONPATH=cli python3 -m memory_custodian.main --help
PYTHONPATH=cli python3 -m memory_custodian.main init --project-root /path/to/project
```

Or install editable and use the console script:

```bash
python3 -m pip install -e .
memory-custodian status
```

Initialize memory in a project:

```bash
memory-custodian init --project-root /path/to/project --with-codex
```

The default initializer creates only the core protocol:

```text
docs/memory/
  manifest.md
  brief.md
  decisions.md
  constraints.md
  do-not-use.md
  inbox.md
```

Create optional modules only when needed:

```bash
memory-custodian init --extended
memory-custodian enable preferences
memory-custodian enable rules/output
memory-custodian enable profile/git
memory-custodian enable area/frontend
```

Read a small context pack:

```bash
memory-custodian read --task planning
memory-custodian read --task implementation
memory-custodian read --task artifact
```

Add memory:

```bash
memory-custodian add "We decided not to use RAG in the MVP." --type decision
```

Forget memory and add a tombstone:

```bash
memory-custodian forget "RAG as MVP architecture" --mode soft
```

Check memory health:

```bash
memory-custodian status
memory-custodian check
```

## Installing The Skill

For Codex, use the installer from this repository:

```bash
./install.sh codex
```

Or manually copy or symlink the skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/memory-custodian" ~/.codex/skills/memory-custodian
```

A managed project should also include a short agent entry point. Use one of:

- `adapters/codex/AGENTS.snippet.md`
- `adapters/claude-code/CLAUDE.snippet.md`
- `adapters/generic/agent-instructions.md`

Keep those entry files small. The complete project memory belongs in `docs/memory/`, not in `AGENTS.md` or `CLAUDE.md`.

## Design Principles

- Read `manifest.md` before substantial project work.
- Load `brief.md` first and only load other files when relevant.
- Keep `archive/` and `inbox.md` out of default context.
- Keep `preferences.md`, `changelog.md`, `rules/`, `profiles/`, `areas/`, and `archive/` optional.
- Prefer proposed memory updates unless the user explicitly asks to remember or forget something.
- Treat deletion as a first-class operation through tombstones in `do-not-use.md`.
- Keep all memory local, plain text, and version-control friendly.
