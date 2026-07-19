# Release Notes

## Unreleased

## v0.8.0 - 2026-07-18

### Reliability and privacy

- Made every managed-file write use same-directory atomic replacement with flush and best-effort file `fsync`.
- Made `forget` preview-first, literal, case-insensitive, broad-match guarded, and structure-safe at complete H2 or bullet boundaries.
- Kept hard and purge records topic-free; purge now includes archive memory and warns about copies outside command scope.

### Context and routing

- Replaced raw token truncation with complete-entry packing, omission counts, and oversized atomic-entry warnings.
- Made initialized-project runtime routing authoritative to `manifest.md`, with exact canonical headings, safe paths, and proactive route validation.
- Kept MemoryCustodian Protocol at 0.5 because existing generated 0.5 manifests already use the required headings and syntax.

### Bootstrap and assurance

- Added idempotent managed blocks for generated `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` bootstraps, including guarded legacy conversion.
- Added Python 3.10/3.13 CI for unit, static contract, repository-memory, and whitespace checks.
- Renamed checker output and documentation to “skill contract check”; it validates static scenarios and does not execute an Agent runtime.

## v0.7.0 - 2026-07-12

### Memory Quality

- Replaced protocol-centric initialization content with a project brief scaffold and empty project-memory files.
- Added status/check detection for uncurated briefs and warnings for machine-specific paths in shared preferences.
- Added post-write budget reporting and 80% warnings.
- Added a 120-token per-decision write gate, long-entry health checks, and explicit `--allow-long` exceptions.

### Routing And Compaction

- Added area-scoped decision writes with `add --type decision --area <name>` and documented scope-first memory routing.
- Load root decisions for implementation, execution, and debugging under protocol 0.5.
- Added a semantic safety gate requiring `--archive-oldest` before age-based decision archival.

### Skill Evals

- Added initialization-quality, scoped-update, and semantic-compaction scenarios based on production memory findings.

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
