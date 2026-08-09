# Memory Quality Audit

Use this audit for production memory, before compaction, or when context loads but fails to help.

Run `memory-custodian check --privacy` and `memory-custodian check --security` for shared-memory audits. These
deterministic pattern scans are not complete secret or personal-data detection. Findings show file, line, type,
and a redacted preview; they never auto-delete or auto-repair content. Continue to apply semantic privacy judgment
before writing shared memory.

Also run the focused Protocol 0.7 checks:

```bash
memory-custodian check --routing
memory-custodian check --reachability
memory-custodian check --freshness
memory-custodian check --conflicts
memory-custodian check --conflicts --merge-base origin/main  # when Git/ref is available
```

## Usefulness

- Verify `brief.md` names the actual project purpose, system shape, and current direction.
- Remove protocol boilerplate from project facts; the manifest and skill already govern MemoryCustodian behavior.
- Compare durable claims with authoritative project files and current code.

## Reachability

- For each active invariant, identify which normal task route loads it.
- Treat an unreachable project-scoped hard constraint as an error; do not auto-promote, move, or invent a matcher.
- Treat malformed or inconsistent reconciliation records as INVALID. Do not ignore malformed headings, duplicate
  fields/blocks, unknown fields, unsorted Entry IDs, or missing admissible Evidence.
- Keep cross-cutting decisions at root and subsystem-specific decisions in matched areas.
- Treat memory that exists but is not loaded for its likely task as unavailable.

## Freshness

- Merge duplicates and update or mark superseded decisions instead of appending contradictions.
- Verify each managed active decision, constraint, rejected approach, and area entry has an active Subject and a
  valid Facet.
- Reject a second active owner for the same normalized Scope, Subject ID, and Facet.
- Audit exact alias and canonical-reference ownership without claiming that fuzzy name similarity proves equality.
- Refresh the brief when project direction changes or several decisions alter the system shape.
- Archive historical rationale only after active invariants remain reachable.
- Treat missing Evidence paths, broken lifecycle/exception/merge relations, and inconsistent reconciliation records
  as explicit findings. Freshness checks never rewrite Evidence or claim factual correctness.

## Structural Conflict Review

- Exact duplicate `Scope + Subject ID + Facet` owners are deterministic conflicts.
- Project/area overlap without a valid `Exception-To`, or overlapping matched areas, requires review.
- Exact Canonical-Ref or normalized alias collisions conflict; fuzzy names and similar prose do not prove equality.
- Git merge-aware review reports concurrent hard-memory changes without choosing a winner by timestamp, Evidence
  count, file order, or merge order.
- Resolve through explicit supersede, valid exception, `distinct` reconciliation, or Subject merge inventory.
  Use `exception add`/`exception remove` and `reconcile preview` for stable inventories, blockers, canonical output,
  and Plan IDs. Protocol 0.7 does not apply multi-file governance changes.
- Require relationship reconciliation records to identify exactly two Entries. For `distinct`, require every
  referenced active Entry to have a different `Scope + Subject + Facet`; it cannot override an exact owner conflict.
- Use one active structural-operand validator across conflict analysis, reconciliation, and governance previews:
  each current owner must be active, have valid scope and Facet, and resolve to exactly one active Subject.
- Apply lifecycle-aware variants for historical relations: validate the active supersession replacement; for
  Subject merge, allow only a superseded historical source's merged Subject and validate the active target and
  matching identity. Do not treat promoted Provisional-Subject/Provisional-Facet as Protocol 0.7 reconciliation input.
- In merge review, validate reconciliation records against each branch's own Entry and Subject graph. Do not reuse
  a syntax-only or merge-base acknowledgement to suppress review of later changes, and exempt only exact validated
  Entry pairs rather than arbitrary subsets of a record.
- Governance preview Plan IDs must bind the exact protocol/schema metadata and every manifest, Entry, Subject, path,
  and reconciliation dependency used in the rendered result. Reject duplicate protocol scalar fields before Entry
  lookup instead of accepting the last value. Require exactly one normalized Protocol H2 section, and reject empty
  or malformed protocol bullets rather than skipping them. Do not claim a resulting governance state while blockers
  remain. Apply the same metadata gate to strict reads, routing checks, governance previews, and ordinary writers.
  Treat wrong-level, missing-whitespace, or extra malformed Protocol heading traces as INVALID; legacy fallback
  requires no trace. Require the canonical current version spelling and reject unsupported future versions at this
  shared gate rather than routing either case with legacy grammar. A
  present section requires a valid version, and Protocol 0.7 requires complete schema, registry, identity, and policy
  fields. Validate recovery candidates before preview and again before apply; reject ambiguous sections for manual
  repair. Exercise a manifest-state by public-entrypoint matrix: preview and local commands must reject before Plan
  IDs or seeds, while status and every focused check must report the same invalid contract.
  Include unsafe routes, fenced and indented heading lookalikes, a genuinely bound local overlay, valid operand IDs,
  structural operand corruption, Plan dependency mutations, recovery failures after legacy-entry discovery, and all
  disabled/unbound/bound/multi-root local-reset states.
- Exercise Markdown-equivalent boundaries: Setext and attached-hash Protocol lookalikes are invalid, fenced and HTML
  comment examples are inert, protocol metadata cannot be indented code, task H3 routes require exactly one canonical
  parent, and duplicate Optional module indexes fail closed. Private-state tests must include symlinks and non-UTF-8
  files, while recovery tests assert that operand failures precede all pending seed creation.
- Include code-span comment markers, backtick and tilde fence-info asymmetry, unknown task H3s, repeated optional
  subsections, sentinel/declaration conflicts, and declarations before a canonical subsection. Assert migration reads
  only normalized memory-contained operands. For local state, test project-id ancestor symlinks, empty/unreadable
  directories, traversal errors, and no-follow descriptor reads. Treat `exclusive-group` as unknown in schema 1.
- Also cover a symlinked `local/` root, exact POSIX `0700`/`0600` modes, duplicate local metadata, mismatched binding
  identity, collision-proof invalid state, migration symlink loops, and human-readable Optional-index preambles.
- Exercise multi-root write/index attempts, missing mandatory scaffold nodes or declarations, indented scalar-shaped
  metadata, duplicate binding JSON keys, and enable/link against already corrupt overlay state.
- Include an actual project directory move, two concurrently live roots, security findings in REVIEW modules, malformed
  formal local Entries, orphan binding-only state, and relative or non-normalized binding roots.
- Test cross-Scope supersession in preview and hand-edited relations; broken or semantically mismatched promotion pairs
  in both ordinary/freshness checks; forbidden local lifecycle fields; and shared/local Entry ID collisions.

## Scope And Portability

- Separate hard constraints from soft preferences.
- Confirm before storing personal, sensitive, credential-like, or workstation-specific information.
- Prefer an abstract constraint and controlled Evidence reference over raw secrets, contract terms, vendor
  identities, or unnecessary numeric limits.
- Avoid shared absolute machine paths; prefer portable commands, conditional profiles, or user-local configuration.
- Keep user/machine preferences in a bound local overlay; verify `--no-local` shared context remains reproducible.

## Budget

- Keep each decision entry within 120 tokens; preserve the choice and reason, not implementation narration.
- Treat `NEAR LIMIT` (80%–100%) as an immediate dry-run maintenance signal; `OVER BUDGET` requires maintenance.
- Split by area before raising global budgets.
- Run `status` and `check` after maintenance and inspect warnings, not only exit status.
