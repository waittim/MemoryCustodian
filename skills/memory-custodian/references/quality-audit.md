# Memory Quality Audit

Protocol 0.8 separates three audit layers and gives their results one
finding/status model. Package 0.12 emits `INFO`, `WARNING`, `ERROR`, and
`BLOCKER` findings; no finding or INFO is `PASS`, WARNING-only is `REVIEW`,
and ERROR/BLOCKER is `FAIL`. Exit classes are 0 for PASS/REVIEW, 1 for an
ERROR/domain failure, and 2 for a BLOCKER or fatal invocation error.

Use `--format json` for automation. The public envelope has
`output_schema_version: 1`; project audit stores `audit_schema_version: 1`
inside `data`. Text and JSON are two renderings of the same audit result. A
forgetting/local-reset/recovery result carries the same versioned
`data.erasure_scope` and bounded `history_check_status` described in
`forgetting-policy.md` and `output-contract.md`.

Project audit checks persistent routing, reachability, evidence, relations,
Subjects, conflicts, budgets, local state, transaction state, and erasure
policy. Invocation audit is the `read --explain` routing result (or
`audit --routing-input`) for one task/path/scope. Repository contract checks
(`check-adapter-contracts.py`, `check-erasure-language.py`, and
`check-version.py`) inspect this source tree; they are not project audit and
do not claim a live agent benchmark.

Use this audit for production memory, before compaction, or when context loads but fails to help.

Run `memory-custodian check --privacy` and `memory-custodian check --security` for shared-memory audits. These
deterministic pattern scans are not complete secret or personal-data detection. Findings show file, line, type,
and a redacted preview; they never auto-delete or auto-repair content. Continue to apply semantic privacy judgment
before writing shared memory.

## Frozen finding registry

Finding codes are public compatibility identifiers. Their spelling and meaning
are frozen for Protocol 0.8; a new code is required when a later release adds a
distinct condition. The producer supplies the severity, so a code such as
`MC-BUDGET-001` may be `WARNING` at `NEAR LIMIT` and `ERROR` when over budget.

| Namespace | Frozen codes and meaning |
| --- | --- |
| Routing/reachability | `MC-ROUTING-001` missing canonical route; `002` enabled module has no activation path; `003` required invocation scope is missing or invalid; `004` unsafe route configuration; `005` required module is missing; `006` active entry is unreachable; `007` invalid protocol/routing contract. `MC-REACH-001` active memory is outside canonical storage or route; `002` hard area memory has no valid activation. |
| Subject identity | `MC-SUBJECT-001` duplicate active Subject ID; `002` duplicate normalized Canonical-Ref; `003` alias has multiple active owners; `004` active Entry references a missing Subject; `005` active Entry references a merged Subject; `006` invalid Subject merge relation. |
| Structural conflict | `MC-CONFLICT-001` duplicate structural owner; `002` project/area overlap lacks Exception-To; `003` invalid exception scope/target; `004` inconsistent reconciliation; `005` concurrent Subject identity collision or invalid Subject reference; `006` invalid exception/reconciliation operand; `007` invalid Entry schema or identity; `008` invalid relation/reconciliation identity; `009` overlapping matched areas; `010` invalid Subject registry. `MC-CONFLICT-000` is the informational clear result. |
| Entry/evidence/relation | `MC-ENTRY-001` malformed or ambiguous canonical Entry; `002` active legacy Entry; `MC-EVIDENCE-001` missing/admission-invalid Evidence; `002` malformed or unavailable Evidence; `MC-RELATION-001` missing/invalid relation target; `002` missing reciprocal lifecycle relation; `003` relation cycle. |
| Transaction/migration/local | `MC-TRANSACTION-001` unfinished or cleanup-pending journal; `002` malformed/unsupported journal; `003` orphan private transaction state; `004` unsafe recovery state. `MC-MIGRATION-001` canonicalization blocker; `002` migration/source binding drift. `MC-LOCAL-001` unbound or wrong-root overlay; `002` overlay cannot safely join a schema transition. |
| Budget/privacy/security | `MC-BUDGET-001` budget is near or over its limit; `MC-PRIVACY-001` machine-specific or personal-data pattern; `MC-SECURITY-001` credential-like or security-sensitive pattern. These scanners are bounded diagnostics, not complete detection. |
| Erasure/history | `MC-ERASURE-001` output claims broader erasure than performed; `002` history inspection unavailable; `003` reachable historical copy detected; `004` bounded inspection found no reachable copy (INFO only and not proof of absence); `005` forgotten topic leaked into semantic metadata, generated names, public JSON, or public errors; `006` local-reset scope exceeds the current project/machine overlay; `007` sensitive repository memory should be minimized or moved to a controlled source. |

The implementation also exposes these stable compatibility diagnostics:
`MC-FRESH-001` unsafe/missing Evidence source, `002` revision drift,
`003` Git freshness unavailable, `004` invalid lifecycle/identity relation,
`005` Subject registry/reference freshness, and `006` reconciliation
freshness; `MC-MERGE-001` through `006` deterministic merge conflicts and
`MC-MERGE-REVIEW-001` through `006` unresolved semantic-review cases;
`MC-INVOCATION-001` invalid command input, `MC-OUTPUT-001`/`002` output
compatibility diagnostics, `MC-PLAN-001`/`002` plan blocker/warning, and
`MC-RUNTIME-001` fatal runtime blocker. These codes remain findings or
diagnostic text only; they do not change the core severity mapping above.

Also run the focused Protocol 0.8 checks:

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
- Require supersession targets to resolve exactly once, reject cycles or chains without an active terminal, and make
  focused freshness surface the same invalid Exception-To and merged-Subject references as conflict analysis.

## Structural Conflict Review

- Exact duplicate `Scope + Subject ID + Facet` owners are deterministic conflicts.
- Project/area overlap without a valid `Exception-To`, or overlapping matched areas, requires review.
- Exact Canonical-Ref or normalized alias collisions conflict; fuzzy names and similar prose do not prove equality.
- Git merge-aware review reports concurrent hard-memory changes without choosing a winner by timestamp, Evidence
  count, file order, or merge order.
- Resolve through explicit supersede, valid exception, `distinct` reconciliation, or Subject merge inventory.
  Use `exception add`/`exception remove` and `reconcile preview` for stable inventories, blockers, canonical output,
  and Plan IDs. Protocol 0.8 applies governance changes only through the
  shared transaction journal and recovery policy.
- Require relationship reconciliation records to identify exactly two Entries. For `distinct`, require every
  referenced active Entry to have a different `Scope + Subject + Facet`; it cannot override an exact owner conflict.
- Use one active structural-operand validator across conflict analysis, reconciliation, and governance previews:
  each current owner must be active, have valid scope and Facet, and resolve to exactly one active Subject.
- Apply lifecycle-aware variants for historical relations: validate the active supersession replacement; for
  Subject merge, allow only a superseded historical source's merged Subject and validate the active target and
  matching identity. Do not treat promoted Provisional-Subject/Provisional-Facet as ordinary reconciliation input.
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
  present section requires a valid version, and Protocol 0.8 requires complete schema, registry, identity, and policy
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
- Test promotion type mismatch, area target ID/storage and Optional-index preview, target-baseline Plan drift,
  supersession cycles, duplicate relation targets, and structurally invalid `add --supersedes` operands.
- Test protocol-shaped raw body/reason/candidate/local/migration input and multiline Subject aliases. Assert that
  unsafe promotion Scope fails before target access, archive IDs block promotion, title text cannot intercept Status
  transition, and directed cycle output names only real edges.
- Test multiline soft-forget topics for field/heading injection and repeated deterministic-guard idempotence. Simulate
  a blocker and broad-risk change between forget preview and lock acquisition for current and compatibility protocols.
- Test whitespace-only active/candidate/local bodies and Subject titles, duplicate typed fields in migration
  candidates, and Protocol 0.5 multiline bullet writes. Fail before shared mutation or private seed creation, and
  require ambiguous migration units to remain unchanged with an apply blocker.
- Test mixed H2/legacy-bullet ordering through forget, compaction, indexing, and budget packing; protocol list bullets
  must stay attached to their H2 owner. Assert newest-first insertion ahead of legacy bullets.
- Inject valid colliding pending Subject, hard-Tombstone, and migration suffix seeds, including two IDs created by one
  migration plan. Test case-only soft-forget repeats, duplicate owners outside do-not-use.md, explicit zero-write
  output, and blank or duplicate Promotion-Requirement fields.

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
