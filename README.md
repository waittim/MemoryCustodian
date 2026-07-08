# MemoryCustodian

Give coding agents durable project memory without bloating every task's context.

MemoryCustodian is a local-first, pure-text memory protocol, skill, and CLI. It stores project context in reviewable Markdown under `docs/memory/`, then uses a manifest to load only the files a task needs.

Memory can grow; context must stay small.

## Quickstart

Pick the install path that matches where you work:

- [Codex local marketplace](#codex-local-marketplace)
- [Claude Code plugin](#claude-code-plugin)
- [Gemini Agent Skill](#gemini-agent-skill)
- [Source checkout / CLI](#source-checkout)

Already in a source checkout? Initialize MemoryCustodian in a project:

```bash
scripts/memory-custodian init --project-root /path/to/project --agent all
scripts/memory-custodian status --project-root /path/to/project
scripts/memory-custodian read --project-root /path/to/project --task planning
```

Or install the CLI in editable mode and use the console script:

```bash
python3 -m pip install -e .
memory-custodian init --project-root /path/to/project --agent all
memory-custodian status --project-root /path/to/project
```

The default initializer creates the core protocol:

```text
docs/memory/
  manifest.md
  brief.md
  decisions.md
  constraints.md
  do-not-use.md
  inbox.md
```

Add a short platform entry with `--with-codex`, `--with-claude`, `--with-gemini`, or `--agent all`. Keep `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` as thin entry points; durable project memory belongs in `docs/memory/`.

## How It Works

MemoryCustodian turns project memory into a small, explicit workflow:

1. **Keep memory in the repo.** Durable context lives in Markdown files under `docs/memory/`, where humans can inspect, diff, review, commit, roll back, and migrate it.
2. **Keep platform files thin.** `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and similar files tell the agent how to find MemoryCustodian instead of importing the whole memory set.
3. **Route through the manifest.** The agent reads `manifest.md`, then `brief.md`, then only the task-relevant files named by the manifest.
4. **Load optional context on purpose.** `rules/`, `profiles/`, and `areas/` are discoverable from the manifest, but not loaded by default.
5. **Record durable changes deliberately.** After meaningful decisions, repeated corrections, or rejected approaches, the agent updates the right memory file or proposes a concise update.
6. **Keep old or raw material out of the way.** `archive/` and `inbox.md` stay out of default context unless the user asks or the task is memory maintenance.

The result is project memory that is inspectable, diffable, portable across agents, and small enough to use in normal coding loops.

## Installation

MemoryCustodian supports local plugin and source-checkout workflows. The plugin bundle exposes the `memory-custodian` skill, CLI wrappers, platform snippets, and a lightweight session-start hook that reminds agents to load memory through the manifest.

### Codex Local Marketplace

For local Codex plugin testing from this checkout, add this repository as a marketplace source:

```bash
codex plugin marketplace add .
```

Then open `/plugins`, switch to `MemoryCustodian Dev`, and install `memory-custodian`.

The repo marketplace points at this checkout, so local edits can be verified in a new Codex thread after reinstalling or refreshing the plugin.

For older local Codex setups that only scan skill folders:

```bash
./install.sh codex
```

### Claude Code Plugin

For local Claude Code plugin testing from this checkout:

```bash
claude --plugin-dir .
```

Direct invocation is namespaced by plugin name:

```text
/memory-custodian:memory-custodian
```

To make the plugin available in future Claude Code sessions without passing `--plugin-dir`, install this checkout into Claude Code's personal skills directory:

```bash
./install.sh claude
```

This symlinks the repository root into `${CLAUDE_HOME:-$HOME/.claude}/skills/memory-custodian`. When the plugin is enabled, `bin/memory-custodian` exposes the bundled CLI wrapper to Claude Code's Bash tool.

### Gemini Agent Skill

For Gemini CLI or compatible Gemini-style agents that discover Agent Skills, install the skill into the personal skills directory:

```bash
./install.sh gemini
```

This symlinks `skills/memory-custodian` into `${GEMINI_HOME:-$HOME/.gemini}/skills/memory-custodian`.

For local development with Gemini skill management, you can also link the skill directly:

```bash
gemini skills link ./skills/memory-custodian
```

Gemini project context files are loaded into prompt context, so keep `GEMINI.md` thin. Do not import `docs/memory/` files from `GEMINI.md`; let MemoryCustodian load project memory through `manifest.md` at task time.

### Source Checkout

For direct local development without a plugin browser, use the bundled wrapper:

```bash
scripts/memory-custodian --help
scripts/memory-custodian status
scripts/memory-custodian read --task planning
```

You can also run the CLI module directly:

```bash
PYTHONPATH=cli python3 -m memory_custodian.main --help
```

Or install editable and use the console script:

```bash
python3 -m pip install -e .
memory-custodian status
```

## The Basic Workflow

Read a small context pack before substantial work:

```bash
memory-custodian read --task planning
memory-custodian read --task implementation
memory-custodian read --task artifact
```

Record durable memory when a decision, constraint, preference, or rejected approach should survive the current chat:

```bash
memory-custodian add "We decided not to use RAG in the MVP." --type decision
memory-custodian forget "RAG as MVP architecture" --mode soft
```

Enable optional memory only when it becomes useful:

```bash
memory-custodian enable preferences
memory-custodian enable rules/output
memory-custodian enable profile/git
memory-custodian enable area/frontend
```

Check, compact, or migrate the local memory set:

```bash
memory-custodian status
memory-custodian check
memory-custodian compact
memory-custodian migrate
```

Use `compact --apply` or `migrate --apply` only after reviewing the dry run.

## What's Inside

- `docs/memory/`: the project-local memory protocol and templates
- `skills/memory-custodian/`: the reusable agent skill
- `cli/memory_custodian/`: a small stdlib-only Python CLI for deterministic memory operations
- `adapters/`: thin entry snippets for Codex, Claude Code, Gemini, and generic agents
- `.codex-plugin/`, `.claude-plugin/`, and `.agents/`: local plugin marketplace metadata
- `evals/memory-custodian/`: skill behavior scenarios and contract checks
- `templates/`: minimal and optional memory module scaffolding

## Philosophy

MemoryCustodian is designed around a few constraints:

- Keep project memory local, plain text, reviewable, and version-control friendly.
- Keep agent entry files thin; do not copy full memory into `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md`.
- Let `manifest.md` decide what is relevant instead of loading every memory file by default.
- Treat deletion as a first-class operation through tombstones in `do-not-use.md`.
- Prefer deterministic CLI operations over background daemons or opaque platform memory.

It deliberately avoids RAG retrieval, embedding indexes, vector databases, cloud-hosted memory, chat-log archiving, automatic full-context loading, and a required Git workflow.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository layout, local checks, packaging commands, and development notes.

## Updating MemoryCustodian

MemoryCustodian tracks three related versions:

- Package version: the CLI, skill bundle, and plugin metadata version.
- Protocol version: the `docs/memory/manifest.md` schema and loading rules.
- Project memory version: the protocol metadata recorded in each initialized project.

`memory-custodian check` reports old or missing protocol metadata. `memory-custodian migrate --apply` updates a project manifest without requiring network access.

## License

MIT License. See `LICENSE` for details.
