# Release Notes

## Unreleased

### Demo and submission materials

- Added the reproducible NightNotes demo fixture and its intentionally failing persistence acceptance test.
- Added a documented Codex GPT-5.6 live evaluation and published demo video.
- Added direct demo commands and Build Week evidence links to the README.

### Plugin metadata and policy

- Added project-specific privacy and terms documents.
- Updated plugin author and policy metadata.

### Compatibility and repository hygiene

- Restored Python 3.10+ support with CI coverage on Python 3.10 and 3.13.
- Removed generated `egg-info` metadata from source control and expanded build-artifact ignores.
- Removed an obsolete demo preparation script that recursively deleted a user-provided target path.

## v0.9.1 - 2026-07-19

### Protocol and compaction safety

- Refuse `init --repair` and `migrate` when project protocol metadata is newer than the installed CLI or cannot be parsed, preventing false compatibility through metadata downgrade.
- Make exact compaction operate on complete column-zero top-level bullet units, preserving nested and continuation content, indentation semantics, and fenced examples.
- Use the same top-level unit rule for inbox counts and show complete candidates in preview output.

### No-op and documentation correctness

- Make repeated `enable` calls true zero-write no-ops, including changelog state.
- Clarify that the Skill selects a supported canonical task category and resolves its files exclusively through the current project manifest.
- Keep MemoryCustodian Protocol at 0.5 because this patch strengthens enforcement without changing the manifest schema.

## v0.9.0 - 2026-07-19

### Semantic boundary

- Removed keyword-based inbox classification. `compact` now reports candidates and applies only exact duplicate and exact tombstone-match cleanup.
- Made the Agent or user responsible for candidate scope, type, confidence, overlap, and semantic promotion.

### Safe initialization and routing

- Replaced memory-file `init --force` with conservative `init --repair` and preview-first `init --replace-existing --apply`.
- Made `enable` preserve existing optional memory and made the Skill follow the current manifest as the sole runtime routing authority.
- Treat an existing memory directory without `manifest.md` as incomplete or corrupted instead of inferring routes.

### Mutation reliability and portability

- Added precomputed mutation plans for multi-file commands, preflight validation, archive-first safety, and explicit partial-completion reporting.
- Routed invalid input and expected filesystem errors to stderr while leaving unexpected programming failures visible.
- Added strict profile/area validation and a Windows Python 3.13 CLI smoke job.
- Kept MemoryCustodian Protocol at 0.5 because the manifest schema and routing syntax remain compatible.

## v0.8.1 - 2026-07-18

### Forget privacy and structural safety

- Hard forget now replaces matching topic-bearing soft tombstones with one generic redacted guard.
- Purge now removes matching topic-bearing soft tombstones instead of leaving the original topic in `do-not-use.md`.
- Plain body and preamble matches are reported as manual-rewrite blockers; `--apply` refuses before the first write, even with `--allow-broad-match`.
- Added regression coverage for soft-to-hard/purge upgrades, whole-memory topic removal, body blockers, preamble blockers, and no-partial-write behavior.

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
