# MemoryCustodian

**Give your coding agents a project memory.**

MemoryCustodian helps agents remember what matters: decisions, constraints, rejected ideas, and project context — across sessions, agents, and teams.

It stores memory as plain Markdown in your repo and routes a bounded context pack using manifest rules, the supplied task category, and explicit scope.

**Durable memory. Minimal context.**

[![Version](https://img.shields.io/badge/version-0.11.0-blue.svg)](https://github.com/waittim/MemoryCustodian/releases/latest)
[![CI](https://img.shields.io/badge/CI-passing-blue.svg)](#)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-agnostic-blue.svg)](#)
[![Design: Offline-first](https://img.shields.io/badge/design-offline--first-blue.svg)](#)
[![Blog](https://img.shields.io/badge/blog-MemoryCustodian-orange.svg)](https://www.zekun.blog/2026/07/01/memory-custodian/)

## Why MemoryCustodian?

New agent sessions often start by relearning decisions your repository already made: architecture constraints, preferred workflows, rejected approaches, and the current project shape. The usual workaround is to paste more into prompts or platform instruction files, which makes every task heavier.

MemoryCustodian moves durable project context into the repository. Humans can review it like code, and agents can load a small context pack before work:

- `brief.md` for the current project shape
- `decisions.md` and `constraints.md` when planning, implementing, or debugging
- `do-not-use.md` when avoiding rejected paths
- Optional `rules/`, `profiles/`, and `areas/` only when the manifest says they apply

*This is project memory, not chat history.*

---

## Quickstart

Just ask your coding agent:

```text
Install the MemoryCustodian skill from https://github.com/waittim/MemoryCustodian, then initialize it.
```

Or initialize your project from the CLI:

```bash
memory-custodian init --project-root /path/to/project --agent all
```

Use `--agent codex`, `--agent claude`, `--agent gemini`, or `--agent all` to create the bootstrap file(s) your agent reads.

Initialization creates the core protocol files in `docs/memory/`:

```text
docs/memory/
  manifest.md    # Routing rules and protocol metadata
  subjects.md    # Stable identity registry for subjects
  brief.md       # High-level project purpose and direction
  decisions.md   # Architectural and technical decisions
  constraints.md # Non-negotiable technical constraints
  do-not-use.md  # Rejected paths, deprecated patterns, and tombstones
  inbox.md       # Candidate memory awaiting confirmation
```

> **Tip:** Curate the initial TODOs in `brief.md` from authoritative project files before relying on memory; `status` and `check` will flag an uncurated brief.

---

## Installation

| Host | Recommended Method |
| :--- | :--- |
| **Codex App / CLI** | Repo-local marketplace from this checkout |
| **Claude Code** | Personal skills directory install or `--plugin-dir` |
| **Gemini Agents** | Agent Skill installed into the personal skills directory |
| **Any Shell / CI** | Editable Python install (`pip install -e .`) or bundled wrapper |

### Codex Local Marketplace

```bash
codex plugin marketplace add .
codex plugin add memory-custodian@memory-custodian-dev
```

### Claude Code Plugin

```bash
# For permanent personal skill install:
./install.sh claude

# Or for local session testing:
claude --plugin-dir .
```

### Gemini Agent Skill

```bash
./install.sh gemini
# Or link directly:
gemini skills link ./skills/memory-custodian
```

### Source Checkout / Python CLI

```bash
python3 -m pip install -e .
# Or use the direct script wrapper:
scripts/memory-custodian --help
```

---

## How It Works

MemoryCustodian turns project memory into a small, explicit workflow:

1. **Bootstrap stays thin.** `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` tell the agent where project memory lives.
2. **The manifest routes context.** The agent reads `manifest.md`, then `brief.md`, then only the task-relevant files named by the manifest.
3. **Optional memory stays opt-in.** `rules/`, `profiles/`, `areas/`, and `archive/` remain out of default context until explicitly triggered.
4. **Updates are scoped.** Cross-cutting decisions stay at root; subsystem knowledge lives in matched `areas/` files.
5. **Active memory is evidence-backed.** Protocol 0.7 gives entries stable IDs and requires user confirmation or project source; unconfirmed agent observations stay candidates in `inbox.md`.
6. **Concurrent mutation is guarded.** Every writer uses an external mutation lock; preview-first commands reject stale Plan IDs.
7. **Conflict identity is structural.** Decisions and constraints reference a stable Subject ID and controlled Facet; display names and aliases are not conflict keys.
8. **Maintenance is deterministic.** Budgets and structure are checked automatically, preserving active invariants before archiving.

## CLI Recipes

### 1. Inspecting & Routing Context

The manifest routes a bounded context pack from explicit task and scope inputs without semantic guessing or LLM ranking.

```bash
# Read context for an implementation task with explanation
memory-custodian read --task implementation --path cli/memory_custodian/read.py --explain

# Strict routing: fails closed on INCOMPLETE, AMBIGUOUS, or INVALID scope
memory-custodian read --task implementation --strict-routing --path cli/memory_custodian/read.py

# Load specific rules and profiles, or omit local overlays
memory-custodian read --task artifact --rule output --profile docs
memory-custodian read --task implementation --no-local
```

Canonical tasks: `general`, `planning`, `implementation`, `artifact`, `preferences`, `history`, and `maintenance`.

Enable path-matched areas:
```bash
memory-custodian enable area/backend --path 'cli/**' --path 'tests/**/*.py'
```

### 2. Recording Durable Memory

Record durable memory when a decision, constraint, preference, or rejected approach should survive the current session:

```bash
# 1. Register a Subject
memory-custodian subject add "Context routing" --kind feature \
  --canonical-ref feature:context-routing --evidence user-confirmed

# 2. Add an active decision or constraint (requires Subject ID and Evidence)
memory-custodian add "We chose manifest-first loading." --type decision \
  --subject MC-SUBJ-... --facet architecture --evidence user-confirmed

# 3. Add area-scoped decision with rationale
memory-custodian add "Persist sync retry backoff." --type decision --area sync \
  --subject MC-SUBJ-... --facet behavior \
  --reason "Keep retries bounded across launches." --evidence repo:docs/architecture.md

# 4. Record an unconfirmed observation as candidate memory in inbox.md
memory-custodian add "The parser may require JSON." --type constraint \
  --candidate --evidence agent-observed

# 5. Supersede an older decision
memory-custodian add "Use the new retry contract." --type decision \
  --subject MC-SUBJ-... --facet interface \
  --supersedes MC-DEC-20260701-a1b2c3d4 --evidence user-confirmed
```

### 3. Forgetting & Deletion

Forgetting is preview-first and enforces explicit deletion scope:

```bash
# Preview soft-forgetting a topic (prints Plan ID)
memory-custodian forget "old deployment note" --mode soft

# Apply confirmed plan
memory-custodian forget "old deployment note" --mode soft --apply --confirm-plan <PLAN_ID>

# Forget a specific entry by stable ID (relation-safe: blocked if referenced)
memory-custodian forget --id MC-DNU-20260801-a1b2c3d4
```

### 4. Health, Quality & Conflict Checks

```bash
# General status and protocol health
memory-custodian status
memory-custodian check

# Focused diagnostics
memory-custodian check --routing
memory-custodian check --reachability
memory-custodian check --freshness
memory-custodian check --privacy
memory-custodian check --security

# Detect structural collisions and duplicate owners
memory-custodian check --conflicts

# Git merge-aware conflict review against a base branch
memory-custodian check --conflicts --merge-base origin/main
```

### 5. Reconciliation & Exceptions

```bash
# Manage Exception-To relations between conflicting constraints
memory-custodian exception add MC-CON-20260801-a1b2c3d4 --to MC-CON-20260801-e5f6a7b8
memory-custodian exception remove MC-CON-20260801-a1b2c3d4

# Preview reconciliation for distinct invariants
memory-custodian reconcile preview --entry MC-CON-... --entry MC-CON-... \
  --resolution distinct --title "Distinct invariants" --evidence user-confirmed
```

### 6. Maintenance & Migration

```bash
# Check budgets and compact oversized memory files
memory-custodian compact

# Archive oldest decision entries when over budget (requires explicit confirmation)
memory-custodian compact --target decisions.md --apply --archive-oldest --confirm-plan <PLAN_ID>

# Preview and apply migration to Protocol 0.7 (and Entry schema 2)
memory-custodian migrate
memory-custodian migrate --apply --confirm-plan <PLAN_ID>
```

---

## Shared and Local Memory

Personal output preferences and machine workflows can live outside the repository under the private user state root:

```bash
# Enable local overlay for this repository's project_id
memory-custodian local enable

# Explicitly bind the normalized repository root
memory-custodian local link
```

- **Precedence:** Shared constraints > Shared decisions > Local preferences.
- **Boundaries:** Local memory cannot override shared hard memory, redefine routes, or serve as a secret store.
- **Privacy:** State directories use POSIX `0700` and regular files use `0600`.

---

## Design Principles

- **Plain Markdown in `docs/memory/`:** Reviewable, diffable, committable, and rollback-safe like code.
- **Thin platform files:** `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` only point to the manifest.
- **Python stdlib only:** Zero third-party runtime dependencies; fully offline and lightweight.
- **No RAG / Vector DB required:** Deterministic manifest routing avoids embedding latency, hallucinations, and ungrounded full-context stuffing.
- **Safe Trust Boundaries:** Memory constrains project conventions but never overrides system instructions, security boundaries, or authorizes destructive external actions.
- **Strict Evidence & Identity:** Stable IDs (`MC-DEC-...`, `MC-SUBJ-...`) and required Evidence prevent phantom rules and accidental overwrites.

---

## Repository Structure

- [`docs/memory/`](docs/memory/): This repository's dogfood memory set.
- [`skills/memory-custodian/`](skills/memory-custodian/): The reusable agent skill and normative [references/](skills/memory-custodian/references/).
- [`cli/memory_custodian/`](cli/memory_custodian/): The Python standard-library CLI implementation.
- [`adapters/`](adapters/): Platform bootstrap snippets for Codex, Claude Code, Gemini, and generic agents.
- [`templates/`](templates/): Minimal and optional memory module scaffolding.
- [`evals/`](evals/): Contract scenarios and deterministic evaluation suites.

---

## Background & History

### See It in Action

The included [NightNotes demo](examples/nightnotes-video-demo) demonstrates a new agent session recovering an existing JSON storage decision, offline/standard-library constraints, and a rejected SQLite approach:

- 📺 [Watch the demo video](https://www.youtube.com/watch?v=mYKzzATlOPw)
- 📊 [Reproducible live evaluation report](docs/evaluations/nightnotes-codex-gpt-5.6.md)

### Built with Codex and GPT-5.6

MemoryCustodian was developed prior to OpenAI Build Week (v0.7.0 baseline) and expanded during Build Week with Codex and GPT-5.6 (v0.8.0 through v0.9.1). Codex accelerated repo-wide implementation across the protocol, CLI, skill adapters, and test suites, while GPT-5.6 assisted in formalizing the boundary between semantic agent judgment and deterministic CLI enforcement.

---

## Upgrading & Versioning

MemoryCustodian tracks three related versions:
- **Package version** (`0.11.0`): CLI, skill bundle, and plugin metadata.
- **Protocol version** (`0.7`): `manifest.md` schema, entry schemas (Schema 2), and routing rules.
- **Project memory version**: Protocol metadata declared in your repository's `manifest.md`.

Run `memory-custodian check` to inspect compatibility, and `memory-custodian migrate` to preview and apply upgrades.

For complete release history and breaking change notes, see [RELEASE-NOTES.md](RELEASE-NOTES.md).

---

## Contributing & License

- See [CONTRIBUTING.md](CONTRIBUTING.md) for local development, test suites, and guidelines.
- Licensed under the [MIT License](LICENSE).
