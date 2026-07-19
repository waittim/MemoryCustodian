# MemoryCustodian

**Give your coding agents a project memory.**

MemoryCustodian helps agents remember what matters: decisions, constraints, rejected ideas, and project context — across sessions, agents, and teams.

It stores memory as plain Markdown in your repo and loads only the pieces needed for the current task.

**Durable memory. Minimal context.**

[![Version](https://img.shields.io/badge/version-0.8.1-blue.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-agnostic-blue.svg)](#)
[![Design: Offline-first](https://img.shields.io/badge/design-offline--first-blue.svg)](#)
[![Architecture: Zero-RAG](https://img.shields.io/badge/architecture-zero--RAG-blue.svg)](#)
[![Blog](https://img.shields.io/badge/blog-MemoryCustodian-orange.svg)](https://www.zekun.blog/2026/07/01/memory-custodian/)

## Why MemoryCustodian?

New agent sessions often start by relearning decisions your repository already made: architecture constraints, preferred workflows, rejected approaches, and the current project shape. The usual workaround is to paste more into prompts or platform instruction files, which makes every task heavier.

MemoryCustodian moves durable project context into the repository. Humans can review it like code, and agents can load a small context pack before work:

- `brief.md` for the current project shape
- `decisions.md` and `constraints.md` when planning, implementing, or debugging
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

Initialization creates a `brief.md` scaffold. Curate its TODOs from authoritative project files before treating memory as ready; `status` and `check` report an uncurated brief.

To repair an existing setup, use `memory-custodian init --repair`. Repair creates missing files and updates known generated metadata or managed bootstrap blocks without overwriting curated memory. Full replacement is deliberately separate and preview-first: inspect `memory-custodian init --replace-existing`, then add `--apply` only when the listed files should be replaced. The legacy memory-file `--force` behavior is not supported; `--force-agent` remains available for recognized managed bootstrap blocks.

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
4. **Updates are scoped.** Cross-cutting decisions stay at root; subsystem knowledge lives in matched `areas/` files and loads only for relevant work.
5. **Maintenance is guarded.** The CLI checks budgets and structure deterministically, while semantic review preserves active invariants before decision history is archived.

The result is project memory that is inspectable, diffable, portable across agents, and small enough to use in normal coding loops.

## Built with Codex and GPT-5.6

MemoryCustodian existed before OpenAI Build Week, with v0.7.0 as the pre-event baseline. During Build Week, I collaborated with Codex using GPT-5.6 to develop the v0.8.0 reliability release and the v0.8.1 privacy patch.

Codex accelerated repo-wide analysis and implementation across the protocol, CLI, agent skill, adapters, and tests. It helped turn reliability concerns into concrete plans, identify edge cases, coordinate changes, and expand regression coverage.

GPT-5.6 was especially useful for reasoning about the boundary between semantic judgment and deterministic enforcement, including complete-entry context packing, safe structured deletion, ambiguous prose handling, and privacy-safe forgetting.

I retained responsibility for the product boundaries, architecture, safety model, and final release decisions.

The Build Week releases added atomic writes, validated routing, idempotent agent bootstraps, privacy-safe forgetting, CI, and expanded reliability tests.

Codex and GPT-5.6 were used to build and validate these releases; they are not runtime dependencies.


## Installation

MemoryCustodian currently supports local plugin and source-checkout workflows. The Codex plugin bundle exposes the `memory-custodian` skill, CLI wrappers, and platform snippets. The Claude Code plugin also includes a lightweight session-start hook that reminds agents to load memory through the manifest.

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
codex plugin add memory-custodian@memory-custodian-dev
```

Alternatively, open the Plugins page in the Codex desktop app, select `MemoryCustodian Dev`, and install `memory-custodian`.

The repo marketplace uses a local source that points at this checkout. Codex caches installed plugins, so after local edits, run the `codex plugin add` command again (or reinstall from the Plugins page), then start a new task to verify the update.

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
3. If `brief.md` is still a generated scaffold, curate it from authoritative project files before relying on it.
4. Load only the task-relevant files named by the manifest.
5. Propose or write durable memory updates after meaningful decisions, repeated corrections, or rejected approaches.

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
memory-custodian add "Persist sync retry backoff." --type decision --area sync --reason "Keep retries bounded across launches."
memory-custodian forget "old deployment note" --mode soft
memory-custodian forget "old deployment note" --mode soft --apply
```

Decision entries have a 120-token guide. Overlong writes are rejected before mutation; first shorten the choice to one or two sentences and the reason to one sentence. Use `--allow-long` only after confirming that splitting the supporting detail would lose essential semantics.

Enable optional memory only when it becomes useful:

```bash
memory-custodian enable preferences
memory-custodian enable rules/output
memory-custodian enable profile/git
memory-custodian enable area/frontend
```

Enabling an optional module never overwrites an existing module file.

Check, compact, or migrate the local memory set:

```bash
memory-custodian status
memory-custodian check
memory-custodian compact
memory-custodian migrate
```

`forget`, `compact`, and `migrate` are preview-first. Add `--apply` only after reviewing the complete plan. Short topics and plans matching multiple semantic units additionally require `forget --allow-broad-match`.

Inbox compaction does not infer decisions, constraints, preferences, or rejected approaches from keywords. The CLI reports candidates and can apply only exact duplicate removal and exact tombstone filtering. An Agent reviews each remaining candidate's scope, type, confidence, and existing overlap, then edits Markdown or calls `add`; `check` validates the result.

Hard forget replaces matching topic-bearing soft tombstones with a generic redacted guard; purge removes them. Matches inside a plain body or preamble are never deleted wholesale: preview reports `Manual rewrite required`, and apply refuses until the text is semantically rewritten.
Decision archival additionally requires semantic review and explicit confirmation with `compact --target decisions.md --apply --archive-oldest`.

## Design Principles

- Memory lives as local Markdown under `docs/memory/`, so it can be reviewed, diffed, committed, and rolled back like code.
- Platform files such as `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` stay thin; they point agents to the manifest instead of storing durable memory.
- Routine CLI operations use Python stdlib only and work offline.
- Expected input and filesystem errors are reported on stderr; unexpected programming failures retain their traceback for debugging.
- CI exercises the Python CLI on Ubuntu and includes a Windows smoke job for platform-sensitive behavior.
- The default architecture avoids RAG retrieval, embedding indexes, vector databases, cloud-hosted memory, chat-log archiving, automatic full-context loading, and required Git workflows.
- Install and update flows may use normal plugin marketplace or package distribution channels.
- Deletion and avoidance are explicit through `do-not-use.md` tombstones.

## What's Inside

- `docs/memory/`: this repository's dogfood memory set
- `skills/memory-custodian/`: the reusable agent skill and detailed reference policies
- `cli/memory_custodian/`: the stdlib-only Python CLI
- `adapters/`: thin entry snippets for Codex, Claude Code, Gemini, and generic agents
- `.codex-plugin/`, `.claude-plugin/`, and `.agents/`: local plugin marketplace metadata
- `evals/memory-custodian/`: static contract scenarios; the checker does not execute Codex, Claude Code, Gemini, or another model runtime
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
