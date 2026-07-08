# Release Notes

## Unreleased

## v0.6.0 - 2026-07-08

### Memory Maintenance

- Added `memory-custodian compact --target <file>` for deterministic review and compaction of over-budget active memory files.
- Added target compaction guidance to `check`, `status`, Claude commands, and compaction policy docs.
- Added tests for target compaction plans, archive output, duplicate bullet cleanup, and status/check guidance.

### Gemini

- Added Gemini bootstrap support through `GEMINI.md`, `adapters/gemini/`, `install.sh gemini`, `memory-custodian init --with-gemini`, and `--agent gemini`.
- Added checks to keep `GEMINI.md` as a thin entry file instead of importing full memory content.

### Documentation

- Refined README initialization guidance, platform entry-file guidance, and contribution documentation.
- Updated dogfood memory and minimal templates to reflect Gemini as a supported agent entry point.

## v0.5.0 - 2026-07-04

### Startup Bootstrap

- Added a lightweight session-start bootstrap hook for plugin hosts that nudges agents toward manifest-first loading without injecting full skill or project memory content.
- Added cross-platform hook dispatch through `hooks/run-hook.cmd`.
- Added a session-bootstrap eval scenario and hardened the skill's startup loading gate.

### Packaging

- Added deterministic Codex plugin archive packaging with `scripts/package-codex-plugin.py`.
- Added Claude local marketplace metadata under `.claude-plugin/marketplace.json`.
- Added package tests for hook output, Claude marketplace metadata, and rootless Codex archives.

### Documentation

- Added a "Why MemoryCustodian?" README section and refreshed the dogfood brief to clarify repeated context setup and agent/developer context gaps.

### Memory Ordering

- Keep dated memory entries newest-first where budget trimming should preserve recent context: decisions, tombstones, and inbox candidates.
- Insert new decision, tombstone, and inbox entries before older entries.
- Preserve current-state files such as manifest, brief, constraints, preferences, rules, profiles, and areas in their semantic order.

### Claude Code

- Added Claude Code plugin-root installation docs and `./install.sh claude`.
- Added `bin/memory-custodian` so Claude Code plugin sessions can expose the CLI wrapper on plugin PATH.
- Added tests for Claude plugin metadata, installer symlink behavior, and the plugin bin wrapper.

## v0.4.1 - 2026-07-04

### Skill Evals

- Added deterministic MemoryCustodian skill eval scenarios for startup loading, memory updates, forgetting, and optional modules.
- Added `scripts/check-skill-evals.py` to guard the skill's core behavior contract and scenario structure.
- Added test coverage for the skill eval checker.

### Documentation

- Documented development checks for unit tests and skill eval drift checks.

## v0.4.0 - 2026-07-03

### Versioning

- Added explicit MemoryCustodian Protocol metadata to generated `manifest.md` files.
- Added `memory-custodian migrate` for deterministic, reviewable protocol upgrades.
- Added offline protocol drift checks to `memory-custodian check`.
- Added Codex and Claude plugin manifests so skill distribution can use plugin/marketplace update flows.
- Added version drift configuration for package and plugin metadata.

### Notes

- Memory operations remain local-first and offline by default.
- Skill, plugin, and CLI installation or update flows may use online distribution channels.
