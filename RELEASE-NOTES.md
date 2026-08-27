# Release Notes

## Unreleased

## v0.11.0 - 2026-08-01

### Deterministic routing for explicit task and scope

- Added Protocol 0.7 routing/conflict schema metadata, canonical task normalization, a normative optional-module
  grammar, case-sensitive cross-platform path globs, and a root-constraints safety baseline.
- Added `read --path/--rule/--explain/--strict-routing`, complete enabled-module dispositions, stable reason codes,
  entry-level budget omissions, and `COMPLETE/INCOMPLETE/AMBIGUOUS/INVALID` diagnostics.
- Invalid routing now remains inside the shared result/disposition model, ordinary non-strict `INCOMPLETE` reads use
  the documented successful inspection exit, and explain exposes inbox/archive policy exclusions.
- Reserved `AMBIGUOUS` for a future versioned policy; routing schema 1 accepts only the four planned optional-module
  keys and rejects the unversioned `exclusive-group` extension as unknown metadata.
- Added routing, reachability, and Evidence/relation freshness checks. They report bounded structural facts and never
  claim automatic semantic retrieval or factual correctness.

### Local overlay and stable ID operations

- Added private repo-external local preferences with explicit project-root binding, shared/local precedence,
  `--no-local`, and preview-only local reset. Local state is not a secret store and cannot override shared hard memory.
- Added canonical entry `list`, `show`, and `forget --id`; preview-only candidate promotion and Subject merge
  inventory remain deferred to the Protocol 0.8 transaction journal.
- Made `forget --id` heading-exact and relation-safe: referencing entries block removal instead of being deleted as
  incidental substring matches, including references in reconciliation records. Generic hard-erasure guards are
  excluded from structural ownership so a successful hard forget cannot invalidate subsequent strict reads.
  Promotion previews now report ID/structural-owner blockers and area-scoped targets.
- Unified topic/ID/purge/local-reset erasure wording and added optional bounded Git history exposure inspection.
  MemoryCustodian does not rewrite Git history or revoke clones, forks, backups, caches, or distributed copies.

### Structural conflict and reconciliation review

- Added deterministic current-worktree conflict codes for duplicate structural owners, canonical Subject collisions,
  invalid exception relations, missing Subject/Facet coverage, and reconciliation-record validation.
- Reconciliation validation now uses a strict canonical parser, and merge-aware review consumes valid resolution
  records only after applying the same full relation validation to each Git revision; invalid branch records and
  unchanged merge-base acknowledgements cannot suppress new review findings.
- Added stable, blocker-aware `exception add`, `exception remove`, and `reconcile preview` workflows while retaining
  the Protocol 0.8 boundary for transactional apply. Relationship resolutions are exact two-Entry acknowledgements;
  `distinct` cannot waive duplicate structural owners; merge review consumes validated exact pairs only.
- Conflict analysis, reconciliation validation, and governance previews share active structural-operand validation
  for scope, unique active Subject resolution, and canonical Facet.
- Supersession records validate the active replacement and retained structural identity. Subject-merge records allow
  superseded historical source references but require a structurally valid active target with matching Scope and
  Facet; promoted provisional identity remains outside the Protocol 0.7 contract.
- Governance previews require exact Protocol/schema compatibility, and their Plan IDs bind manifest, Entry,
  Subject-registry, reconciliation, content, and path dependencies used by the rendered result. Duplicate protocol
  H2 sections, scalar fields, empty values, and malformed scalar bullets are invalid rather than silently skipped or
  accepted with last-value-wins behavior. Strict reads, routing checks, and governance previews consume the same
  metadata validation. Wrong-level, missing-whitespace, or extra malformed Protocol heading traces cannot fall back
  to legacy mode. The current version must use the canonical `0.7` spelling; equivalent noncanonical spellings and
  unsupported future versions fail the shared gate.
  The shared mutation guard rejects ambiguous, malformed, or newer metadata before ordinary writers change files;
  explicit migration/repair flows may read incomplete inputs but must produce a fully valid candidate before preview
  or apply. A present section requires a valid version, and Protocol 0.7 requires all schema, registry, identity, and
  policy fields. Ambiguous sections require manual repair. Exception removal does not predict a resulting review
  while blockers remain. All public preview, local-overlay, status, and focused diagnostic entrypoints perform this
  preflight before operand lookup, Plan ID rendering, or seed creation; failed migration syntax checks leave no
  pending local identity state.
- Combined metadata and route validation for every current-project preflight and recovery candidate. Markdown-aware
  section scans ignore fenced examples and HTML comments without accepting Setext, attached-hash, or indented-code
  lookalikes as the Protocol H2. Canonical task routes require one `Load by task` parent and the Optional module index
  is unique. Bound local data is never selected through an ambiguous manifest identity. Promotion and Subject-merge
  previews validate structural operands and bind rendered text dependencies; local reset distinguishes disabled,
  unbound, bound, and multi-root review states, hashes private bytes without following symlinks, and binds the local
  content it would eventually remove. Migration reads all operands before creating preview seeds and derives missing
  task routes from the initialization template's single authority.
- Tightened the finite manifest lexer for code spans, standalone HTML comments, and backtick/tilde fences; ambiguous
  or unclosed constructs fail closed. Optional/task subsection topology is canonical and contradictory sentinels are
  invalid. Migration reads only contained normalized declarations. Local overlay access rejects a symlinked
  project-id ancestor, and reset inventory binds directories, reports traversal failures, and reads files through
  no-follow descriptors.
- Extended that boundary to the `local/` directory itself and enforced exact POSIX `0700`/`0600` modes before local
  status, reads, or reset approval. Local manifest scalars and binding identity are unique and matching. Migration
  normalizes symlink-loop failures without creating preview state and preserves human-readable Optional-index prose.
- Made multi-root `REVIEW` diagnostic-only for writes and explicit local indexing. Required local scaffold components
  and declared modules must exist; local scalars require canonical placement; bindings reject duplicate JSON keys;
  and enable/link validate existing state before reporting success or changing root bindings.
- Restored moved-project recovery by replacing one nonexistent stale binding on explicit link while retaining REVIEW
  for concurrently live roots. REVIEW modules remain eligible for security/privacy diagnostics, formal local Entries
  reuse schema/Evidence validation, binding roots must be normalized absolute paths, and orphan bindings become
  blocker-aware REVIEW/reset state instead of DISABLED.
- Completed relation integrity checks: supersession preserves Scope as well as Subject/Facet; promotion validates
  reciprocal links, lifecycle, Candidate-Type, Scope, and provisional identity in both ordinary and freshness checks.
  Local Entries are active-only with no governance relations, and shared/local Entry ID collisions fail closed across
  status, read, check, indexing, enable/link, and local writes.
- Promotion preview now validates the rendered active target, uses `MC-AREA` for area decisions, previews required
  Optional-index changes, and binds target existence/content. Supersession planning rejects invalid source operands;
  relation audit requires unique targets and acyclic chains ending at an active replacement. Freshness also promotes
  invalid exceptions and active merged-Subject references to errors.
- Made Entry/body and Subject/alias rendering line-safe with parse round-trip checks, preventing raw Markdown from
  creating protocol fields, Entries, or merge state. Ambiguous column-zero Entry body lines use the explicit,
  versioned `memory-custodian-body-v1` Markdown fence; legacy `&#8283;` content remains literal. Promotion now validates Scope/containment before target access,
  checks archive IDs, anchors Status transition, and reports cycles in real edge order.
- Closed the remaining write-boundary cases: rendered typed bodies and Subject titles must be non-empty, legacy
  multiline bullets remain one unit, and migration applies the shared schema/storage checks to every prospective
  Entry while treating ambiguous legacy units as blockers before apply.
- Soft forget now renders guards and changelog bullets through line-safe serializers, treats a case-equivalent
  deterministic guard as an idempotent no-op, and blocks conflicting IDs. Preview and apply consume one authoritative
  build result; the lock-held rebuild rechecks blockers and broad-match risk for both Protocol 0.7 and compatibility
  writes before any mutation.
- Unified mixed H2/legacy-bullet walking across forget, compaction, indexing, and budget packing, without detaching
  Evidence or other protocol lists from their owner. New guards retain newest-first ordering ahead of legacy bullets.
- Random Subject, hard-forget Tombstone, and migration Entry IDs are checked against existing and same-plan owners on
  every build. Soft guard identity now follows case-insensitive matching, duplicate owners block idempotence, zero-write
  apply reports a no-op, and candidate Promotion-Requirement is unique and non-empty.
- Added matched-context conflict gates and optional read-only merge-base review for cross-branch structural collisions
  and concurrent hard-memory changes requiring human reconciliation.
- Subject names, timestamps, Evidence counts, file order, and prose similarity never choose a winner. This release
  does not provide complete natural-language contradiction detection or automatic conflict resolution.

### Conservative migration and agent workflow

- Added preview-first Protocol 0.6 to 0.7 migration that preserves IDs, Evidence, custom task routes, descriptions,
  and optional modules; legacy prose triggers become safe `explicit-only` declarations without guessed matchers.
- Updated templates, adapters, Skill references, examples, evals, and dogfood memory for strict scope-aware startup.

## v0.10.0 - 2026-07-28

### Subject identity, routing, and erasure alignment

- Added `subjects.md` as a non-routed, plain-text registry with stable Subject IDs, exact normalized alias and
  canonical-reference ownership, and preview-first add, rename, and alias mutations.
- Added controlled Facets and active-owner admission based on normalized `Scope + Subject ID + Facet`, including
  explicit supersede transitions and legacy coverage reporting.
- Made routing provenance structured and deterministic for manifest routes and explicit profile/area inputs,
  without hidden relevance scoring.
- Added a unified `ErasureScope` for forget previews and apply output. Hard and purge state that managed-memory
  removal does not rewrite Git history or revoke distributed copies.
- Added prevention-first sensitive-memory guidance: prefer minimal abstract constraints and controlled Evidence
  references over copying raw secrets, contract text, or unnecessary vendor details.
- Extended same-version migration to install Subject protocol metadata and registry scaffolding without inferring
  semantic identity from legacy prose.

### Evidence-backed entry governance

- Added Protocol 0.6 manifests with entry schema 1, persistent UUIDv4 project identity, and evidence-required admission.
- Added stable Entry IDs, structured active/candidate entries, source-path validation, candidate-only unconfirmed evidence, and linked supersede updates.
- Kept Protocol 0.5 freeform units readable and migrated structured legacy decisions with `legacy-unverified` evidence without claiming semantic verification.

### Concurrent and preview-safe mutation

- Added one bootstrap-to-permanent project mutation guard for every writer, including repair, enable, migration,
  Subject operations, and Protocol 0.5 compatibility writes. The manifest project ID installed during repair is
  now exactly the identity of the permanent lock being held.
- Added repo-relative canonical Plan IDs with private execution and public preview representations. Ordinary plans
  expose base/output SHA-256 digests; hard and purge public plans redact raw arguments, digests, and matching topic
  text in path/blocker metadata while a random private nonce keeps confirmation identifiers resistant to topic
  dictionary attacks.
- Generate migration project identity from a random UUIDv4 persisted in platform state for the preview/apply pair, preventing identical legacy projects from sharing locks or future overlays.
- Rebuild complete replacement, supersede, compaction, forgetting, and migration plans after acquiring the mutation lock; legacy destructive replacement now requires migration first.
- Hold the normalized-path bootstrap lock through permanent-lock acquisition and mutation-plan rebuild, eliminating
  the repair/enable handoff window.
- Recover malformed private lock residue only through explicit stale-lock recovery after a five-minute safety age,
  and opportunistically expire abandoned preview seeds after seven days.
- Added real-process concurrent-add and stale-plan regression tests. These tests verify deterministic safety properties, not a live cross-agent benchmark or database transaction semantics.
- Added deterministic `OK`, `NEAR LIMIT`, and `OVER BUDGET` states; writes at 80% or above emit a no-write maintenance preview instead of relying on an agent to calculate the threshold.
- Made same-day archives idempotent: one canonical file note, no repeated batch wrappers, merged changelog date headings, and newest-first archived changelog order.

### Trust, privacy, and security boundaries

- Documented that memory cannot elevate authority or override system, user, safety, or permission boundaries.
- Added redacted deterministic checks for common credential-like patterns, machine paths, personal email, and phone-number shapes. These checks are not complete secret detection and never auto-delete content.
- Redact every recognized sensitive span on a finding line before rendering any preview, and revalidate manually
  edited active/candidate Evidence during `check`.
- Validate formal structured entries as schema claims: reject duplicate fields, missing Status/Scope/Evidence,
  missing or mismatched typed bodies, duplicate relations, and contradictory lifecycle fields.
- Keep area decision IDs as `MC-AREA` while area constraints, preferences, and rejected approaches retain
  `MC-CON`, `MC-PREF`, and `MC-DNU`; validate type, body, storage path, and Scope bidirectionally.
- Generate hard-forget Tombstone suffixes from random repo-external preview seeds rather than topic-derived hashes;
  protect both formal and provisional Subject references during purge.
- Restrict private state directories/files to `0700`/`0600` on POSIX and reject symlink, foreign-owner, or
  non-regular private state targets.
- Keep ordinary scan output summary-only while `--security` and `--privacy` reveal redacted locations; validate inbox statuses and promotion/supersede relation integrity.

### Demo and submission materials

- Added the reproducible NightNotes demo fixture and its intentionally failing persistence acceptance test.
- Added a documented Codex GPT-5.6 live evaluation and published demo video.
- Added direct demo commands and Build Week evidence links to the README.

### Plugin metadata and policy

- Added project-specific privacy and terms documents.
- Updated plugin author and policy metadata.

### Compatibility and repository hygiene

- Restored Python 3.10+ support with CI coverage across every supported minor from Python 3.10 through 3.14.
- Run CI on every pushed branch and include version-drift verification plus explicit privacy/security checks.
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
