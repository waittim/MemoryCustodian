# Decisions

## 2026-06-30 - Establish local text memory foundation
Decision:
Store project memory as Markdown files inside each project, defaulting to `docs/memory/`. Keep `AGENTS.md`, `CLAUDE.md`, and similar platform files as thin entry points. Build the MVP CLI with Python standard library modules only.

Reason:
This keeps memory local, inspectable, portable, easy to diff, and usable for routine operations without network access.

## 2026-07-02 - Adopt minimal-first v0.3 protocol
Decision:
Default initialization should create only the six core memory files: `manifest.md`, `brief.md`, `decisions.md`, `constraints.md`, `do-not-use.md`, and `inbox.md`.

Reason:
Small projects should not receive optional workflow files until they are useful. Optional memory belongs behind explicit enablement.

Implications:
- `preferences.md`, `changelog.md`, `rules/`, `profiles/`, `areas/`, and `archive/` are optional.
- `manifest.md` is the loading source of truth.
- CLI support includes `enable` and `check`.

Status:
active

## 2026-07-02 - Keep Skill instructions operational
Decision:
Keep `SKILL.md` focused on agent execution: when to use the skill, which files to read, how to update memory, how to compact or forget, and which files not to load by default.

Reason:
`SKILL.md` is an execution entry point for agents, not a project positioning page.

Implications:
- Avoid prominent negative lists in the Skill body.
- Put full non-goals in `README.md` and reference docs.
- Keep hard architecture constraints in `docs/memory/constraints.md`.

Status:
active

## 2026-07-03 - Keep memory changelog newest first
Decision:
Keep `changelog.md` entries in reverse chronological order, with the newest maintenance event at the top.

Reason:
History recaps and memory maintenance should surface the latest project memory changes first.

Status:
active

## 2026-07-03 - Separate offline memory from online distribution
Decision:
Memory operations should work offline by default, but skill, plugin, and CLI installation or update flows may use network distribution.

Reason:
Local-first project memory should not require network access at runtime, while update delivery can use package managers, marketplaces, git, or other online distribution channels.

Status:
active

## 2026-07-03 - Version package and memory protocol separately
Decision:
Track both the MemoryCustodian package version and the project memory protocol version. Generated manifests should record `protocol_version`, `initialized_with`, and `last_migrated_with`; CLI checks should report stale or missing protocol metadata.

Reason:
Updating the CLI or skill does not automatically update memory files already copied into user projects. Explicit protocol metadata lets users and agents detect when a project needs migration.

Implications:
- Package/plugin version uses SemVer.
- Memory protocol version advances when generated memory structure or loading rules change.
- Project migrations should be deterministic, reviewable, and offline by default.

Status:
active

## 2026-07-03 - Index optional modules in manifest
Decision:
List enabled `rules/`, `profiles/`, and `areas/` files in a lightweight manifest optional module index.

Reason:
Agents need to discover which optional memory files exist before they can decide whether to load them. The index exposes paths and trigger conditions without loading optional file contents into default context.

Status:
active

## 2026-07-03 - Require memory directories under docs
Decision:
Project memory directories must live under `docs/`; `docs/memory/` remains the default managed directory.

Reason:
Visible documentation paths are easier for teams and agents to discover, review, diff, commit, and roll back than hidden root-level memory directories.

Status:
active
