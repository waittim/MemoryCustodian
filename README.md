# MemoryCustodian

Repo-native plain-text memory governance for coding agents.

MemoryCustodian is a local-first project memory protocol, skill, and CLI. It lets coding agents carry durable project context through human-readable Markdown files while keeping each task's loaded context small.

Memory can grow; context must stay small.

## Quick Start

From this checkout, initialize MemoryCustodian in another project:

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

The default initializer creates the core protocol only:

```text
docs/memory/
  manifest.md
  brief.md
  decisions.md
  constraints.md
  do-not-use.md
  inbox.md
```

Add a short agent bootstrap with `--with-codex`, `--with-claude`, `--with-gemini`, or the snippets in `adapters/`. Keep `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` as entry points; durable project memory belongs in `docs/memory/`.

## How It Works

1. A project includes a short agent entry file, such as `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md`.
2. Before substantial work, the agent reads `docs/memory/manifest.md`.
3. The agent reads `brief.md`, then loads only the task-relevant files named by the manifest.
4. Optional `rules/`, `profiles/`, and `areas/` files are discoverable from the manifest without being loaded by default.
5. After meaningful decisions, repeated corrections, or rejected approaches, the agent updates the appropriate memory file or proposes a concise update.
6. `archive/` and `inbox.md` stay out of default context unless the user asks or the task is memory maintenance.

The result is project memory that is inspectable, diffable, portable across agents, and small enough to use in normal coding loops.

## Why MemoryCustodian?

Agent work often spans many threads, chats, and tools. Without a project-local memory layer, useful context lives in the developer's head, scattered chat history, or third-party docs that agents may not load at the right time. Every new session starts with repeated project explanation.

MemoryCustodian keeps that context in the repository, in plain Markdown, with manifest-guided loading. It narrows the gap between the context advantage developers carry in their heads and the context agents can reliably access.

That gives teams:

- Less repeated context setup across threads and chats
- A smaller context gap between developers and agents
- Inspectable memory that humans can read, review, and edit
- Small task context through manifest-driven loading
- Portable workflows across Codex, Claude Code, Gemini-style agents, and generic agents
- Reviewable memory changes that can be diffed, committed, rolled back, or migrated
- Offline operation without RAG, embeddings, vector databases, cloud storage, or a background daemon

## What It Provides

- A project memory file protocol under `docs/memory/`
- A reusable agent skill at `skills/memory-custodian/SKILL.md`
- Platform entry snippets for Codex, Claude Code, Gemini, and generic agents
- A small Python CLI for deterministic memory operations
- Skill behavior eval scenarios under `evals/memory-custodian/`
- Minimal templates for core memory files and optional templates for extra modules
- Codex and Claude Code plugin metadata plus Gemini Agent Skill install support

## Installation

MemoryCustodian currently supports local plugin and source-checkout workflows. The plugin bundle exposes the `memory-custodian` skill, the `scripts/memory-custodian` CLI wrapper, a Claude Code PATH wrapper at `bin/memory-custodian`, Gemini Agent Skill installation, and a lightweight session-start hook that reminds agents to perform manifest-first loading when project memory exists.

### Codex Local Marketplace

For local Codex plugin testing from this checkout, add this repository as a marketplace source:

```bash
codex plugin marketplace add .
```

Then open `/plugins`, switch to `MemoryCustodian Dev`, and install `memory-custodian`.

The repo marketplace points at this checkout, so local edits can be verified in a new Codex thread after reinstalling or refreshing the plugin.

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

### Codex Skill Symlink Fallback

For older local Codex setups that only scan skill folders:

```bash
./install.sh codex
```

Or manually symlink the skill folder:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/memory-custodian" ~/.codex/skills/memory-custodian
```

## Project Bootstrap

A managed project should include a short agent entry point. Use one of:

- `adapters/codex/AGENTS.snippet.md`
- `adapters/claude-code/CLAUDE.snippet.md`
- `adapters/gemini/GEMINI.snippet.md`
- `adapters/generic/agent-instructions.md`

Or initialize a project with a platform entry:

```bash
memory-custodian init --project-root /path/to/project --with-codex
memory-custodian init --project-root /path/to/project --with-claude
memory-custodian init --project-root /path/to/project --with-gemini
```

Custom memory directories, if explicitly configured, must still live under `docs/`.

## CLI Usage

Read a small context pack:

```bash
memory-custodian read --task planning
memory-custodian read --task implementation
memory-custodian read --task artifact
```

Add durable memory:

```bash
memory-custodian add "We decided not to use RAG in the MVP." --type decision
```

Forget memory and add a tombstone:

```bash
memory-custodian forget "RAG as MVP architecture" --mode soft
```

Enable optional memory only when it becomes useful:

```bash
memory-custodian enable preferences
memory-custodian enable rules/output
memory-custodian enable profile/git
memory-custodian enable area/frontend
```

Enabling a `rules/`, `profiles/`, or `areas/` file also adds a short entry to `manifest.md`, so agents can discover optional memory without loading its contents.

Create the optional starter files in one step when you want the scaffolding:

```bash
memory-custodian init --extended
```

Check memory health:

```bash
memory-custodian status
memory-custodian check
```

Compact memory:

```bash
memory-custodian compact
memory-custodian compact --apply
memory-custodian compact --target decisions.md
memory-custodian compact --target decisions.md --apply
```

Use `compact` without `--target` for inbox cleanup. Use `compact --target <file>` when an active file is over budget; review the dry run before applying changes.

Upgrade an existing memory folder to the current protocol:

```bash
memory-custodian migrate
memory-custodian migrate --apply
```

## Memory And Agent Layers

MemoryCustodian is repository-native project memory. It is separate from user-local memories that an agent platform may provide.

Use the layers together:

- Use `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or another platform entry file for instructions the agent must follow every time in a repository.
- Use user-local agent memories, when available, for personal preferences and stable cross-project context.
- Use MemoryCustodian for project-level decisions, constraints, rejected approaches, and task-routed context that should travel with the repository.

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

## Versioning And Updates

MemoryCustodian tracks three related versions:

- Package version: the CLI, skill bundle, and plugin metadata version.
- Protocol version: the `docs/memory/manifest.md` schema and loading rules.
- Project memory version: the protocol metadata recorded in each initialized project.

`memory-custodian check` reports old or missing protocol metadata. `memory-custodian migrate --apply` updates the project manifest without requiring network access.

Memory operations are local-first and offline by default. Skill, plugin, and CLI installation or update flows may use online distribution channels such as GitHub, package managers, or agent plugin marketplaces.

## Repository Layout

```text
MemoryCustodian/
  .codex-plugin/plugin.json       # Codex plugin manifest
  .claude-plugin/plugin.json      # Claude plugin metadata
  .claude-plugin/marketplace.json # Claude local development marketplace metadata
  GEMINI.md                       # Gemini context entry for this repository
  .agents/plugins/marketplace.json # Repo-local plugin marketplace for testing
  hooks/                          # Lightweight session-start bootstrap for plugin hosts
  skills/memory-custodian/        # Reusable agent skill
  adapters/                       # Codex, Claude Code, Gemini, and generic entry snippets
  cli/memory_custodian/           # Python CLI implementation
  bin/memory-custodian            # Claude plugin PATH wrapper
  scripts/memory-custodian        # Plugin-safe CLI wrapper
  scripts/package-codex-plugin.py # Deterministic Codex plugin archive builder
  evals/memory-custodian/         # Skill behavior eval scenarios and contract checks
  templates/minimal/              # Core protocol templates
  templates/extended/             # Optional memory module scaffolding
  docs/memory/                    # Dogfood memory for this repository
  tests/                          # Focused stdlib unittest suite
```

## Development Checks

Run the unit tests:

```bash
PYTHONPATH=cli python3 -m unittest discover -s tests
```

Check that the skill's core behavior contract and eval scenario pack have not drifted:

```bash
python3 scripts/check-skill-evals.py
```

Build a deterministic Codex plugin archive:

```bash
python3 scripts/package-codex-plugin.py --allow-dirty --output /tmp/memory-custodian.zip
```

## Principles

- Read `manifest.md` before substantial project work.
- Load `brief.md` first and only load other files when relevant.
- Use the manifest optional module index to discover enabled `rules/`, `profiles/`, and `areas/` without loading their contents.
- Keep `archive/` and `inbox.md` out of default context.
- Keep `preferences.md`, `changelog.md`, `rules/`, `profiles/`, `areas/`, and `archive/` optional.
- Prefer proposed memory updates unless the user explicitly asks to remember or forget something.
- Treat deletion as a first-class operation through tombstones in `do-not-use.md`.
- Keep all memory local, plain text, and version-control friendly.

## License

MIT License. See `LICENSE` for details.
