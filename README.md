# MemoryCustodian

**Give your coding agents a project memory.**

MemoryCustodian helps agents remember what matters: decisions, constraints, rejected ideas, and project context — across sessions, agents, and teams.

It stores memory as plain Markdown in your repo and routes a bounded context pack using manifest rules, the supplied task category, and explicit scope.

**Durable memory. Minimal context.**

[![Version](https://img.shields.io/badge/version-0.11.0-blue.svg)](https://github.com/waittim/MemoryCustodian/releases/latest)
[![CI](https://github.com/waittim/MemoryCustodian/actions/workflows/ci.yml/badge.svg)](https://github.com/waittim/MemoryCustodian/actions/workflows/ci.yml)
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
- optional `rules/`, `profiles/`, and `areas/` only when the manifest says they apply

This is project memory, not chat history.

## See It in Action

The included [NightNotes demo](examples/nightnotes-video-demo) shows a new agent
session recovering an existing JSON storage decision, offline and
standard-library constraints, and a rejected SQLite approach.

[Watch the published demo](https://www.youtube.com/watch?v=mYKzzATlOPw).

```bash
scripts/memory-custodian read \
  --project-root examples/nightnotes-video-demo \
  --task planning

scripts/memory-custodian compact \
  --project-root examples/nightnotes-video-demo
```

On Windows, install the console command first and replace
`scripts/memory-custodian` with `memory-custodian`.

The demo README includes the intentionally failing acceptance test, the exact
Codex prompt, expected memory, and success criteria so the flow can be
reproduced without the submission form. The result is recorded as a
[reproducible live evaluation](docs/evaluations/nightnotes-codex-gpt-5.6.md),
not presented as a benchmark.

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

To repair an existing setup, use `memory-custodian init --repair`. Repair creates missing files and updates known generated metadata or managed bootstrap blocks without overwriting curated memory. Full replacement is deliberately separate and preview-first: inspect `memory-custodian init --replace-existing`, then add `--apply` only when the listed files should be replaced. Protocol 0.5 memory must be migrated before destructive replacement so preview and apply share a permanent project identity. The legacy memory-file `--force` behavior is not supported; `--force-agent` remains available for recognized managed bootstrap blocks.

The default initializer creates the core protocol:

```text
docs/memory/
  manifest.md
  subjects.md
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
6. **Active memory is evidence-backed.** Protocol 0.7 gives formal entries stable IDs and requires user confirmation or a project source; unconfirmed agent observations stay candidates in `inbox.md`.
7. **Concurrent mutation is explicit.** Every writer uses one bootstrap-to-project guard outside the repository; legacy compatibility writes remain format-compatible but are serialized, and preview-first Protocol 0.7 commands reject stale Plan IDs.
8. **Conflict identity is structural.** Managed decisions, constraints, and rejected approaches reference a stable Subject ID and controlled Facet; display names and aliases are not conflict keys.

The result is project memory that is inspectable, diffable, portable across agents, and small enough to use in normal coding loops.

## Built with Codex and GPT-5.6

MemoryCustodian existed before OpenAI Build Week, with v0.7.0 as the pre-submission baseline. During Build Week, I collaborated with Codex using GPT-5.6 to develop versions 0.8.0 through 0.9.1.

Codex accelerated repo-wide analysis and implementation across the protocol, CLI, agent skill, adapters, documentation, and tests. It helped turn reliability concerns into concrete plans, coordinate multi-file changes, identify edge cases, and expand regression coverage.

GPT-5.6 was especially useful for defining the boundary between semantic judgment and deterministic enforcement. The agent or user decides meaning, scope, confidence, and memory promotion; the CLI validates structures, previews mutations, and applies bounded operations safely.

I retained responsibility for the product boundaries, architecture, safety model, and final release decisions.

The Build Week releases added atomic writes, complete-entry context packing, validated routing, privacy-safe forgetting, conservative initialization, precomputed mutation plans, protocol downgrade guards, structure-preserving compaction, cross-platform CI, and expanded tests.

Codex and GPT-5.6 were used to build and validate these releases; they are not runtime dependencies.

### Build Week scope

- Pre-submission baseline: v0.7.0, released July 12, 2026
- Build Week releases: v0.8.0 through v0.9.1, released July 18–19, 2026
- Comparison range: [v0.7.0...v0.9.1](https://github.com/waittim/MemoryCustodian/compare/v0.7.0...v0.9.1)
- Submission snapshot: [`openai-build-week-submission-final`](https://github.com/waittim/MemoryCustodian/tree/openai-build-week-submission-final)
- Core Codex session evidence: [NightNotes live evaluation](docs/evaluations/nightnotes-codex-gpt-5.6.md) and the [published demo video](https://www.youtube.com/watch?v=mYKzzATlOPw)

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
memory-custodian read --task implementation \
  --path cli/memory_custodian/read.py --explain
memory-custodian read --task implementation --strict-routing \
  --path cli/memory_custodian/read.py
memory-custodian read --task artifact --rule output --profile docs
memory-custodian read --task implementation --no-local
```

The manifest routes a bounded context pack from explicit task and scope inputs. For the same manifest, canonical
task, paths, and explicit modules, routing is deterministic and inspectable. The CLI does not score task prose with
keywords, embeddings, semantic similarity, or an LLM, and path matching does not prove semantic relevance.

Canonical tasks are `general`, `planning`, `implementation`, `artifact`, `preferences`, `history`, and
`maintenance`. Generated manifests load `brief.md` plus root `constraints.md` as the project-wide safety baseline.
Rules activate through declared canonical tasks or explicit `--rule`; profiles are explicit-only; areas activate
through declared POSIX path globs or explicit `--area`. Enable a matched area with:

```bash
memory-custodian enable area/backend --path 'cli/**' --path 'tests/**/*.py'
```

`read --explain` assigns every enabled module one disposition and a stable reason code, while separately listing
whole entries omitted by budgets. If a substantial task has path-routed areas but supplies neither paths nor an
explicit area, routing is `INCOMPLETE`. Ordinary inspection may show the safety baseline; `--strict-routing` rejects
the pack for substantial work. Ordinary `INCOMPLETE` inspection exits successfully with a structured warning;
strict `INCOMPLETE` exits nonzero. `AMBIGUOUS` and `INVALID` fail rather than falling back to natural-language
guessing, and invalid inputs are rendered through the same disposition/reason model instead of bypassing it with
an unstructured parser error. Explain also makes the normal-context exclusion of inbox candidates and archives
explicit. Default Protocol 0.7 manifests do not declare mutually exclusive routes. A customized manifest may place
path-activated areas in one `exclusive-group`. With no explicit selection, multiple path-activated members are
`AMBIGUOUS`; one explicit member selects that member and suppresses the other automatic activations; multiple
explicit members are `AMBIGUOUS`. At most one member of an exclusive group is loaded:

```markdown
- `areas/client.md`
  - activation: path-or-explicit
  - paths: `src/**`
  - exclusive-group: runtime
- `areas/server.md`
  - activation: path-or-explicit
  - paths: `src/**`
  - exclusive-group: runtime
```

`exclusive-group` is valid only for path-activated areas. It is never inferred from names, paths, or task prose.

Record durable memory when a decision, constraint, preference, or rejected approach should survive the current chat:

```bash
memory-custodian subject add "Context routing" --kind feature \
  --canonical-ref feature:context-routing --evidence user-confirmed
# Review the plan, then apply with --apply --confirm-plan <PLAN_ID>.
memory-custodian subject list

memory-custodian add "We chose manifest-first loading." --type decision \
  --subject MC-SUBJ-... --facet architecture --evidence user-confirmed
memory-custodian add "Persist sync retry backoff." --type decision --area sync \
  --subject MC-SUBJ-... --facet behavior \
  --reason "Keep retries bounded across launches." --evidence repo:docs/architecture.md
memory-custodian add "The parser may require JSON." --type constraint \
  --candidate --evidence agent-observed
memory-custodian add "Use the new retry contract." --type decision \
  --subject MC-SUBJ-... --facet interface \
  --supersedes MC-DEC-20260701-a1b2c3d4 --evidence user-confirmed
# Review its Plan ID, then repeat with:
#   --apply --confirm-plan <PLAN_ID>
memory-custodian forget "old deployment note" --mode soft
memory-custodian forget "old deployment note" --mode soft \
  --apply --confirm-plan <PLAN_ID>
```

Decision entries have a 120-token guide. Overlong writes are rejected before mutation; first shorten the choice to one or two sentences and the reason to one sentence. Use `--allow-long` only after confirming that splitting the supporting detail would lose essential semantics.

Enable optional memory only when it becomes useful:

```bash
memory-custodian enable preferences
memory-custodian enable rules/output
memory-custodian enable profile/git
memory-custodian enable area/frontend --path 'frontend/**'
```

Enabling an optional module never overwrites an existing module file.

Check, compact, or migrate the local memory set:

```bash
memory-custodian status
memory-custodian check
memory-custodian check --privacy
memory-custodian check --security
memory-custodian check --routing
memory-custodian check --reachability
memory-custodian check --freshness
memory-custodian check --conflicts
memory-custodian check --conflicts --merge-base origin/main
memory-custodian compact
memory-custodian migrate
memory-custodian list --status active
memory-custodian show MC-CON-...
memory-custodian forget --id MC-DNU-...
memory-custodian exception add MC-CON-20260801-a1b2c3d4 --to MC-CON-20260801-e5f6a7b8
memory-custodian exception remove MC-CON-20260801-a1b2c3d4
memory-custodian reconcile preview --entry MC-CON-... --entry MC-CON-... --resolution distinct --title "Distinct invariants" --evidence user-confirmed
```

Protocol 0.7 retains entry and Subject schema version 1. Formal entries use stable IDs such as
`MC-DEC-20260728-a1b2c3d4`; active writes require Evidence;
`agent-observed` and `conversation-unconfirmed` can create only candidates, which normal task context never loads.
Managed active decisions, constraints, and rejected approaches also reference a stable `MC-SUBJ` identity and a
controlled Facet. `subjects.md` is shared protocol metadata, not normal task context. Exact normalized alias and
Canonical-Ref collisions are rejected, as is a second active owner for the same Scope+Subject+Facet. Renaming a
Subject preserves its ID. v0.11 does not infer that different names are semantically equivalent and does not
automatically resolve Subjects created independently on different branches.
The full canonical Facet vocabulary remains available for every managed entry type; the explicit compatibility
matrix is an extension boundary, not a claim that v0.11 imposes narrower type-specific exclusions.
Legacy 0.5 prose and bullets remain readable after conservative migration and are reported as legacy coverage rather
than silently rewritten. Migration assigns a random UUIDv4 once, persists it outside the repository between preview
and apply, and also upgrades clearly structured decisions in enabled `areas/*.md` files.

`forget`, `compact`, `migrate`, and destructive replacement are preview-first. The preview prints repo-relative
target files, operations, warnings, blockers, and a Plan ID. Ordinary plans include base/output digests; hard and
purge plans keep raw arguments, paths, blockers, and digests in the private execution representation and redact
matching sensitive topic text from public output. Protocol 0.7 apply requires
`--confirm-plan <PLAN_ID>` and rechecks the plan under the project mutation lock; an intervening edit refuses all
writes. Short topics and plans matching multiple semantic units additionally require `forget --allow-broad-match`.

Private locks and preview seeds live outside the repository in directories restricted to the current user. State
directories are forced to mode `0700` and regular files to `0600` on POSIX; symlink or non-regular state targets are
rejected. Pending seeds contain random identifiers, not raw memory messages or forget topics. Seeds older than
seven days are removed opportunistically on the next private-plan-state access; an expired preview must be
generated again. A malformed lock can be recovered only through explicit stale-lock recovery after a five-minute
safety age.

Inbox compaction does not infer decisions, constraints, preferences, or rejected approaches from keywords. The CLI reports candidates and can apply only exact duplicate top-level bullet-unit removal and exact tombstone filtering. Each unit includes its continuation and nested lines; nested bullets are never cleaned up independently. An Agent reviews each remaining candidate's scope, type, confidence, and existing overlap, then edits Markdown or calls `add`; `check` validates the result.

Hard forget removes matching active managed memory and replaces matching topic-bearing soft tombstones with a generic
redacted guard. Purge additionally searches managed `archive/` content and removes matching guards. Every preview
states the selected managed scope and explicitly reports that Git history, clones, forks, backups, and caches are not
modified or revoked. Forgetting controls what future agents receive through MemoryCustodian; it is not repository-wide
erasure. A generic hard-erasure `MC-TOMB` is a content-minimized governance guard, not a Subject/Facet structural
owner. `forget --id` selects only the canonical unit whose heading owns that ID; live entries and reconciliation
records that reference the selected entry become blockers and are never removed as incidental substring matches. `--history-check`
optionally inspects reachable history in the current local Git repository without
changing it. `unavailable` is not a PASS, and `no-reachable-copy-detected` is limited evidence—not proof that no
copy exists in other refs, remotes, clones, forks, backups, caches, or dangling objects.

## Shared and Local Memory

Personal output preferences and machine workflows can live outside the repository under the private state root.
Use `memory-custodian local enable`, then explicitly bind the normalized repository root with `local link`. A copied
repository sharing the public `project_id` is `UNBOUND` and cannot read an existing overlay. `--no-local` renders a
reproducible shared-only pack.

Shared constraints and tombstones outrank shared decisions/rules, which outrank local preferences/profiles. Local
memory cannot redefine shared routes, override hard memory, grant authority, or serve as a secret store. Protocol
0.7 `local reset` is preview-only and describes only the current machine/current project overlay; transactional
apply requires Protocol 0.8 and never claims to affect other machines or backups.

## Structural Conflicts and Reconciliation

`check --conflicts` detects exact `Scope + Subject ID + Facet` duplicate owners, Canonical-Ref and alias collisions,
invalid Subjects, broken `Exception-To`, and inconsistent reconciliation records. A project/area overlap without an
explicit exception is REVIEW; a deterministic duplicate owner is CONFLICT. `read` shows the matched-context status,
and strict substantial reads refuse unresolved conflicts.

Reconciliation records use a strict canonical parser: malformed headings, duplicate fields or blocks, unknown
fields, unsorted/duplicate Entry IDs, invalid Evidence, duplicate record IDs, and inconsistent relations are
`MC-CONFLICT-008 INVALID` rather than silently ignored. Relationship resolutions (`superseded`, `exception`, and
`subject-merged`) acknowledge exactly two Entry IDs. A multi-entry `distinct` record acknowledges only pairwise
different active `Scope + Subject + Facet` identities; it cannot waive an exact structural-owner conflict.
Conflict analysis, reconciliation validation, and governance previews share the same active structural-operand
checks for scope, uniquely resolved active Subject, and canonical Facet.

`exception add` and `exception remove` provide stable, blocker-aware `Exception-To` previews. `reconcile preview`
renders a canonical record, complete entry inventory, relation-consistency blockers, and stable Plan ID. These are
read-only Protocol 0.7 workflows: cross-file apply still requires the Protocol 0.8 transaction journal. They reject
older/newer protocols, duplicate protocol scalar fields, and missing or mismatched Entry, Subject, routing, or
conflict schema metadata. Their Plan IDs
bind the manifest plus every Entry, registry, and reconciliation dependency used to render the preview, so the
identifier changes whenever its observable decision state changes.

When Git is available, `check --conflicts --merge-base <ref>` compares semantic units changed on both sides. It
distinguishes deterministic collisions from concurrent hard-memory changes requiring semantic reconciliation.
Short files and timestamps improve reviewability but do not resolve contradictions or establish precedence.
Merge review revalidates reconciliation syntax, referenced Entry IDs, and resolution relations independently in
each Git revision. Invalid target-branch records cannot suppress REVIEW, and acknowledgements inherited unchanged
from the merge base do not waive later concurrent changes. Explicit supersede, exception, `distinct`
reconciliation, and Subject merge inventory are auditable. Protocol 0.7
does not apply Subject merges, reconciliation acknowledgements, Exception-To mutations, or multi-file promotions;
those transactions require the Protocol 0.8 journal.
Decision archival additionally requires semantic review and explicit confirmation with `compact --target decisions.md --apply --archive-oldest`.
Plain `check` reports redacted privacy/security finding counts; use `check --privacy` or `check --security` to show
redacted file and line locations.

Budget reporting uses three deterministic states: `OK` below 80%, `NEAR LIMIT` from 80% through 100%, and
`OVER BUDGET` above 100%. A write that reaches either maintenance state prints a dry-run review and target
compaction command, but never automatically rewrites, archives, or applies semantic maintenance.

## Design Principles

- Memory lives as local Markdown under `docs/memory/`, so it can be reviewed, diffed, committed, and rolled back like code.
- Platform files such as `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` stay thin; they point agents to the manifest instead of storing durable memory.
- Routine CLI operations use Python stdlib only and work offline.
- Expected input and filesystem errors are reported on stderr; unexpected programming failures retain their traceback for debugging.
- CI exercises every supported Python minor from 3.10 through 3.14 on Ubuntu and runs a Windows smoke job for each
  of those versions to cover platform-sensitive behavior.
- The default architecture avoids RAG retrieval, embedding indexes, vector databases, cloud-hosted memory, chat-log archiving, automatic full-context loading, and required Git workflows.
- Install and update flows may use normal plugin marketplace or package distribution channels.
- Deletion and avoidance are explicit through `do-not-use.md` tombstones.
- Project memory may constrain project work but cannot override system or current user instructions, safety, or
  permission boundaries. It never authorizes destructive actions, external uploads, secret access, Git publishing,
  releases, or privilege escalation.
- Privacy and security checks are deterministic, redacted pattern scans—not complete secret detection and not
  automatic remediation.
- Repository memory is not a secret store. Prefer references to controlled source documents and abstract constraints
  such as “subject to external vendor policy” over credentials, contract text, party identifiers, or unnecessary
  vendor limits. Prevent sensitive writes instead of relying on later forgetting.

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

`memory-custodian check` reports old or missing protocol metadata. Preview `memory-custodian migrate`, then apply
the Protocol 0.6-to-0.7 migration with `memory-custodian migrate --apply --confirm-plan <PLAN_ID>` without requiring network
access. Migration preserves custom routes, budgets, optional modules, archive content, and legacy freeform units.

See [RELEASE-NOTES.md](RELEASE-NOTES.md) for recent changes.

## License

MIT License. See `LICENSE` for details.
