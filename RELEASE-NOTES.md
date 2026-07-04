# Release Notes

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
