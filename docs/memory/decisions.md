# Decisions

## 2026-06-30 - Use local text memory
Decision:
Store durable project memory as Markdown files under `docs/`, defaulting to `docs/memory/`. Keep `AGENTS.md`, `CLAUDE.md`, and similar files as thin bootstraps.

Reason:
Memory should be local, inspectable, portable, diffable, and easy to roll back.

## 2026-07-02 - Keep the core protocol minimal
Decision:
Default initialization creates only `manifest.md`, `brief.md`, `decisions.md`, `constraints.md`, `do-not-use.md`, and `inbox.md`.

Reason:
Small projects should not receive optional workflow files until they are useful.

Implications:
- Optional preferences, changelog, rules, profiles, areas, and archive stay disabled until enabled.
- `manifest.md` is the loading source of truth and indexes optional modules.

## 2026-07-02 - Keep Skill instructions operational and concise
Decision:
Keep `SKILL.md` focused on agent execution. Put detailed policy in references, README, or memory files.

Reason:
`SKILL.md` is an execution entry point for agents, not a project positioning page.

## 2026-07-03 - Separate offline memory from distribution
Decision:
Memory operations should work offline by default, but skill, plugin, and CLI installation or update flows may use network distribution.

Reason:
Local-first project memory should not require network access at runtime, while update delivery can use package managers, marketplaces, git, or other online distribution channels.

## 2026-07-03 - Version package and memory protocol separately
Decision:
Track package/plugin version separately from the memory protocol version. Generated manifests record `protocol_version`, `initialized_with`, and `last_migrated_with`.

Reason:
Updating the CLI or skill does not automatically update memory files already copied into projects.

Implications:
- Memory protocol version advances when generated memory structure or loading rules change.
- Project migrations should be deterministic, reviewable, and offline by default.

## 2026-07-04 - Make plugin distribution self-contained
Decision:
Codex plugin support should include a repo-local marketplace entry, plugin metadata/assets, and a bundled CLI wrapper. Project memory still lives in `docs/memory/` and is activated by thin project bootstrap files.

Reason:
Plugin installation should make the reusable workflow and CLI helper available without copying project memory into the plugin or requiring a global console script.
