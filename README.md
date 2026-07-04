# MemoryCustodian

Repo-native memory governance for agents.

MemoryCustodian is a local-first, pure-text project memory protocol, skill, and CLI. It lets coding agents share durable project context through human-readable Markdown files while keeping each task's loaded context small.

Memory can grow; context must stay small.

## Why MemoryCustodian?

Agent work often spans many threads, chats, and tools. Without a project-local memory layer, the useful context lives in the developer's head, scattered chat history, or third-party docs that agents may not load at the right time. That makes every new session start with repeated project explanation.

MemoryCustodian keeps that context in the repository, in plain Markdown, with manifest-guided loading so agents can pick up the right background without pulling the whole project history into every task. It narrows the gap between the context advantage developers carry in their heads and the context agents can reliably access, making development and loop engineering smoother.

That gives teams:

- Less repeated context setup across threads and chats
- A smaller context gap between developers and agents
- Inspectable memory that humans can read, review, and edit
- Small task context through manifest-driven, task-specific loading
- Portable agent workflows across Codex, Claude Code, and generic agents
- Reviewable memory changes that can be diffed, committed, rolled back, or migrated
- Offline operation without RAG, embeddings, vector databases, cloud storage, or a background daemon

## What It Provides

- A project memory file protocol under `docs/memory/`
- A reusable Codex-compatible skill at `skills/memory-custodian/SKILL.md`
- Platform entry snippets for Codex, Claude Code, and generic agents
- A small Python CLI for deterministic memory operations
- Skill behavior eval scenarios under `evals/memory-custodian/`
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
  .codex-plugin/plugin.json      # Codex plugin manifest
  .claude-plugin/plugin.json     # Claude plugin metadata
  .claude-plugin/marketplace.json # Claude local development marketplace metadata
  .agents/plugins/marketplace.json # Repo-local plugin marketplace for testing
  hooks/                         # Lightweight session-start bootstrap for plugin hosts
  skills/memory-custodian/        # Reusable agent skill
  adapters/                       # Codex, Claude Code, and generic entry snippets
  cli/memory_custodian/           # Python CLI implementation
  bin/memory-custodian            # Claude plugin PATH wrapper
  scripts/memory-custodian        # Plugin-safe CLI wrapper
  scripts/package-codex-plugin.py # Deterministic Codex plugin archive builder
  evals/memory-custodian/         # Skill behavior eval scenarios and contract checks
  templates/minimal/              # Core protocol templates
  templates/extended/             # Optional memory module templates
  docs/memory/                    # Dogfood memory for this repository
  tests/                          # Focused stdlib unittest suite
```

## Quick Start

From a source checkout or installed plugin bundle, use the bundled wrapper:

```bash
scripts/memory-custodian --help
scripts/memory-custodian init --project-root /path/to/project
```

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

Custom memory directories, if explicitly configured, must still live under `docs/`.

Create optional modules only when needed:

```bash
memory-custodian init --extended
memory-custodian enable preferences
memory-custodian enable rules/output
memory-custodian enable profile/git
memory-custodian enable area/frontend
```

Enabling a `rules/`, `profiles/`, or `areas/` file also adds a short entry to `manifest.md` so agents can discover that optional memory without loading its contents.

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

Upgrade an existing memory folder to the current protocol:

```bash
memory-custodian migrate
memory-custodian migrate --apply
```

## Installing The Plugin

MemoryCustodian is packaged for Codex and Claude Code with different installation surfaces. Codex uses the repo-local plugin marketplace below. Claude Code can load this checkout as a plugin root because it contains `.claude-plugin/plugin.json`, `skills/`, and `bin/`. Projects still use a short `CLAUDE.md` bootstrap to point agents at their local memory folder.

The plugin bundle exposes:

- the `memory-custodian` skill under `skills/`
- a plugin-safe CLI wrapper at `scripts/memory-custodian`
- a Claude plugin PATH wrapper at `bin/memory-custodian`
- a lightweight session-start bootstrap under `hooks/`
- Codex metadata in `.codex-plugin/plugin.json`
- Claude metadata in `.claude-plugin/plugin.json`
- Claude local marketplace metadata in `.claude-plugin/marketplace.json`
- a repo-local marketplace entry in `.agents/plugins/marketplace.json`

### Codex Repo Marketplace

For local plugin testing from this checkout, add this repository as a Codex marketplace source:

```bash
codex plugin marketplace add .
```

Then open `/plugins`, switch to `MemoryCustodian Dev`, and install `memory-custodian`.

The repo marketplace points at this checkout as the plugin source, so local edits are easy to verify in a new Codex thread after reinstalling or refreshing the plugin.

### Claude Code Plugin

For local plugin testing from this checkout, start Claude Code with the plugin directory:

```bash
claude --plugin-dir .
```

The skill is namespaced by the plugin name, so direct invocation is:

```text
/memory-custodian:memory-custodian
```

To make the plugin available in future Claude Code sessions without passing `--plugin-dir`, install this checkout into Claude Code's personal skills directory:

```bash
./install.sh claude
```

This symlinks the repository root into `${CLAUDE_HOME:-$HOME/.claude}/skills/memory-custodian`, where Claude Code can load it as a plugin-in-skills-directory on the next session. When the plugin is enabled, `bin/memory-custodian` exposes the bundled CLI wrapper to Claude Code's Bash tool.

The plugin also includes a small session-start hook that reminds agents to perform manifest-first MemoryCustodian loading when a project memory folder exists; it does not inject full skill or project memory contents.

Then add the project bootstrap from `adapters/claude-code/CLAUDE.snippet.md` to each target project's `CLAUDE.md`, or initialize a project with:

```bash
memory-custodian init --project-root /path/to/project --with-claude
```

The Codex marketplace commands above are still Codex-specific.

### Source Checkout

For direct local development without the plugin browser, use the source checkout:

```bash
scripts/memory-custodian status
scripts/memory-custodian read --task planning
```

Or install editable and use the console script:

```bash
python3 -m pip install -e .
memory-custodian status
```

### Codex Skill Symlink Fallback

For older local Codex setups that only scan skill folders, use the installer:

```bash
./install.sh codex
```

Or manually symlink the skill folder:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/memory-custodian" ~/.codex/skills/memory-custodian
```

## Project Bootstrap

A managed project should also include a short agent entry point. Use one of:

- `adapters/codex/AGENTS.snippet.md`
- `adapters/claude-code/CLAUDE.snippet.md`
- `adapters/generic/agent-instructions.md`

Keep those entry files small. The complete project memory belongs in `docs/memory/`, not in `AGENTS.md` or `CLAUDE.md`.

## Versioning And Updates

MemoryCustodian tracks three related versions:

- Package version: the CLI, skill bundle, and plugin metadata version.
- Protocol version: the `docs/memory/manifest.md` schema and loading rules.
- Project memory version: the protocol metadata recorded in each initialized project.

`memory-custodian check` reports old or missing protocol metadata. `memory-custodian migrate --apply` updates the project manifest without requiring network access.

Memory operations are local-first and offline by default. Skill, plugin, and CLI installation or update flows may use online distribution channels such as GitHub, package managers, or agent plugin marketplaces.

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

## Design Principles

- Read `manifest.md` before substantial project work.
- Load `brief.md` first and only load other files when relevant.
- Use the manifest optional module index to discover enabled `rules/`, `profiles/`, and `areas/` without loading their contents.
- Keep `archive/` and `inbox.md` out of default context.
- Keep `preferences.md`, `changelog.md`, `rules/`, `profiles/`, `areas/`, and `archive/` optional.
- Prefer proposed memory updates unless the user explicitly asks to remember or forget something.
- Treat deletion as a first-class operation through tombstones in `do-not-use.md`.
- Keep all memory local, plain text, and version-control friendly.
