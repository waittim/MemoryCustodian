# Memory Changelog

Entries are newest first.

## 2026-07-08
- Prepared package and plugin version 0.6.0 for the Gemini adapter and target compaction release.

## 2026-07-05
- Added target compaction for over-budget active memory files and semantically compacted decisions memory to stay within budget.

## 2026-07-04
- Added lightweight session-start bootstrap memory guidance, deterministic Codex archive packaging, Claude local marketplace metadata, and package/plugin version 0.5.0.
- Changed dated memory entries to newest-first where appropriate: decisions, tombstones, and inbox candidates.
- Added Claude Code plugin-root installation docs, installer support, bin wrapper, and packaging tests.
- Bumped package and plugin version metadata to 0.4.1 for the skill eval release.
- Added deterministic MemoryCustodian skill eval scenarios and a checker for core behavior-contract drift.
- Added Codex plugin support files: repo-local marketplace, plugin asset, CLI wrapper, and plugin packaging tests.
- Compressed dogfood memory files and minimal templates to keep high-frequency context short.
- Added the memory-update reminder to generated agent bootstrap snippets.

## 2026-07-03
- Added v0.4 protocol metadata, migration checks, release notes, and plugin manifests.
- Clarified that offline constraints apply to memory operations, not skill/plugin update distribution.
- Established memory changelog entries as newest-first.
- Added manifest optional module indexing for enabled rules, profiles, and areas.
- Enforced project memory directories under `docs/`, with `docs/memory/` as the default.

## 2026-07-02
- Updated repository memory to the v0.3 minimal-first protocol.
- Recorded the decision to keep `SKILL.md` focused on operational agent instructions.

## 2026-06-30
- Initialized MemoryCustodian dogfood memory files.
- Captured MVP constraints, decisions, preferences, and tombstones from the planning outline.
