# MemoryCustodian

**Give your coding agents a project memory.**

MemoryCustodian helps agents remember what matters: decisions, constraints, rejected ideas, and project context — across sessions, agents, and teams

It stores memory as plain Markdown in your repo and loads only the pieces needed for the current task.

**Durable memory. Minimal context.**

## Why MemoryCustodian?

New agent sessions often start by relearning decisions your repository already made: architecture constraints, preferred workflows, rejected approaches, and the current project shape. The usual workaround is to paste more into prompts or platform instruction files, which makes every task heavier.

MemoryCustodian moves durable project context into the repository. Humans can review it like code, and agents can load a small context pack before work:

- `brief.md` for the current project shape
- `decisions.md` and `constraints.md` when planning
- `do-not-use.md` when avoiding rejected paths
- optional `rules/`, `profiles/`, and `areas/` only when the manifest says they apply

This is project memory, not chat history.

## Quickstart

Just ask your coding agent:

```text
Install the MemoryCustodian skill from https://github.com/waittim/MemoryCustodian, then initialize it.
```

Or pick the install path that matches your agent:

- [Codex local marketplace](#codex-local-marketplace)
- [Claude Code plugin](#claude-code-plugin)
- [Gemini Agent Skill](#gemini-agent-skill)
- [Source checkout / CLI](#source-checkout)

After installation, run `init` once for each target project:

```bash
memory-custodian init --project-root /path/to/project --agent all
```

Use `--agent codex`, `--agent claude`, `--agent gemini`, or `--agent all` to create the small bootstrap file(s) your agent reads.

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

Platform files are bootstraps; durable memory belongs in `docs/memory/`.

## How It Works

MemoryCustodian turns project memory into a small, explicit workflow:

1. **Bootstrap stays thin.** `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and similar files tell the agent where project memory lives.
2. **The manifest routes context.** The agent reads `manifest.md`, then `brief.md`, then only the task-relevant files named by the manifest.
3. **Optional memory stays opt-in.** `rules/`, `profiles/`, `areas/`, and `archive/` remain out of the default context until they are explicitly relevant.
4. **Updates are deliberate.** After meaningful decisions, repeated corrections, or rejected approaches, the agent updates the right memory file or proposes a concise update.
5. **Maintenance is deterministic.** The CLI checks, compacts, forgets, and migrates memory without a background service or opaque platform store.

The result is project memory that is inspectable, diffable, portable across agents, and small enough to use in normal coding loops.

## Installation

MemoryCustodian currently supports local plugin and source-checkout workflows. The plugin bundle exposes the `memory-custodian` skill, CLI wrappers, platform snippets, and a lightweight session-start hook that reminds agents to load memory through the manifest.


| Host                | Best path                                                     |
| ------------------- | ------------------------------------------------------------- |
| Codex App or CLI    | Repo-local marketplace from this checkout                     |
| Claude Code         | Plugin directory for local testing, or personal skill install |
| Gemini-style agents | Agent Skill installed into the personal skills directory      |
| Any shell           | Source checkout wrapper or editable Python install            |




### Codex Local Marketplace

For local Codex plugin testing from this checkout, add this repository as a marketplace source:

```bash
codex plugin marketplace add .
```

Then open `/plugins`, switch to `MemoryCustodian Dev`, and install `memory-custodian`.

The repo marketplace points at this checkout, so local edits can be verified in a new Codex thread after refreshing the plugin.

Older local Codex setups that only scan skill folders can run `./install.sh codex`.

### Claude Code Plugin

Requires the Claude Code CLI to be installed and available on `PATH`.

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

Requires Gemini CLI or a compatible Gemini-style skill manager to be installed and available on `PATH`.

For Gemini CLI or compatible Gemini-style agents that discover Agent Skills, install the skill into the personal skills directory:

```bash
./install.sh gemini
```

This symlinks `skills/memory-custodian` into `${GEMINI_HOME:-$HOME/.gemini}/skills/memory-custodian`.

For local development with Gemini skill management, you can also link the skill directly:

```bash
gemini skills link ./skills/memory-custodian
```

Use the generated `GEMINI.md` as a thin bootstrap. Do not import `docs/memory/` files from project context; let MemoryCustodian load memory through `manifest.md` at task time.

### Source Checkout

For direct local development without a plugin browser, use the bundled wrapper:

```bash
scripts/memory-custodian --help
scripts/memory-custodian init --project-root /path/to/project --agent all
scripts/memory-custodian status --project-root /path/to/project
scripts/memory-custodian read --project-root /path/to/project --task planning
```

Or install editable with Python 3.10+ and use the console script:

```bash
python3 -m pip install -e .
memory-custodian init --project-root /path/to/project --agent all
memory-custodian status --project-root /path/to/project
memory-custodian read --project-root /path/to/project --task planning
```



## What Runs Automatically

After installation and project initialization, MemoryCustodian is meant to be agent-operated. A capable agent with the skill or platform bootstrap should do this before substantial work:

1. Read `docs/memory/manifest.md`.
2. Read `docs/memory/brief.md`.
3. Load only the task-relevant files named by the manifest.
4. Propose or write durable memory updates after meaningful decisions, repeated corrections, or rejected approaches.

Humans do not need to run `memory-custodian read` before every task. The CLI commands below are for setup checks, manual inspection, maintenance, or deterministic operations you ask an agent to run.

## CLI Recipes

The examples below use the `memory-custodian` console script. From a source checkout, replace it with `scripts/memory-custodian`.

Inspect a context pack:

```bash
memory-custodian read --task planning
memory-custodian read --task implementation
memory-custodian read --task artifact
```

Record durable memory when a decision, constraint, preference, or rejected approach should survive the current chat:

```bash
memory-custodian add "We chose manifest-first loading." --type decision
memory-custodian forget "old deployment note" --mode soft
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

## Data Model

- Memory files are local Markdown under `docs/memory/`.
- Platform instruction files stay thin and point agents to the manifest.
- The CLI uses Python stdlib only and keeps routine memory operations offline.
- The default architecture avoids RAG retrieval, embedding indexes, vector databases, cloud-hosted memory, chat-log archiving, automatic full-context loading, and required Git workflows.
- Install and update flows may use normal plugin marketplace or package distribution channels.
- Deletion and avoidance are explicit through `do-not-use.md` tombstones.



## What's Inside

- `docs/memory/`: this repository's dogfood memory set
- `skills/memory-custodian/`: the reusable agent skill and detailed reference policies
- `cli/memory_custodian/`: the stdlib-only Python CLI
- `adapters/`: thin entry snippets for Codex, Claude Code, Gemini, and generic agents
- `.codex-plugin/`, `.claude-plugin/`, and `.agents/`: local plugin marketplace metadata
- `evals/memory-custodian/`: skill behavior scenarios and contract checks
- `examples/`: small project layouts for common host environments
- `templates/`: minimal and optional memory module scaffolding



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository layout, local checks, packaging commands, and development notes.

## Updating MemoryCustodian

MemoryCustodian tracks three related versions:

- Package version: the CLI, skill bundle, and plugin metadata version
- Protocol version: the `docs/memory/manifest.md` schema and loading rules
- Project memory version: the protocol metadata recorded in each initialized project

`memory-custodian check` reports old or missing protocol metadata. `memory-custodian migrate --apply` updates a project manifest without requiring network access.

See [RELEASE-NOTES.md](RELEASE-NOTES.md) for recent changes.

## License

MIT License. See `LICENSE` for details.