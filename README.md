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
  .codex-plugin/plugin.json      # Codex plugin manifest
  .agents/plugins/marketplace.json # Repo-local plugin marketplace for testing
  skills/memory-custodian/        # Reusable agent skill
  adapters/                       # Codex, Claude Code, and generic entry snippets
  cli/memory_custodian/           # Python CLI implementation
  scripts/memory-custodian        # Plugin-safe CLI wrapper
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

MemoryCustodian is packaged as a Codex plugin. The plugin bundle exposes:

- the `memory-custodian` skill under `skills/`
- a plugin-safe CLI wrapper at `scripts/memory-custodian`
- Codex metadata in `.codex-plugin/plugin.json`
- a repo-local marketplace entry in `.agents/plugins/marketplace.json`

### Codex Repo Marketplace

For local plugin testing from this checkout, add this repository as a Codex marketplace source:

```bash
codex plugin marketplace add .
```

Then open `/plugins`, switch to `MemoryCustodian Dev`, and install `memory-custodian`.

The repo marketplace points at this checkout as the plugin source, so local edits are easy to verify in a new Codex thread after reinstalling or refreshing the plugin.

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

### Skill Symlink Fallback

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

## Design Principles

- Read `manifest.md` before substantial project work.
- Load `brief.md` first and only load other files when relevant.
- Use the manifest optional module index to discover enabled `rules/`, `profiles/`, and `areas/` without loading their contents.
- Keep `archive/` and `inbox.md` out of default context.
- Keep `preferences.md`, `changelog.md`, `rules/`, `profiles/`, `areas/`, and `archive/` optional.
- Prefer proposed memory updates unless the user explicitly asks to remember or forget something.
- Treat deletion as a first-class operation through tombstones in `do-not-use.md`.
- Keep all memory local, plain text, and version-control friendly.
