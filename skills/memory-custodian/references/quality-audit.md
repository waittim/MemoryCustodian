# Memory Quality Audit

Use this audit for production memory, before compaction, or when context loads but fails to help.

Run `memory-custodian check --privacy` and `memory-custodian check --security` for shared-memory audits. These
deterministic pattern scans are not complete secret or personal-data detection. Findings show file, line, type,
and a redacted preview; they never auto-delete or auto-repair content. Continue to apply semantic privacy judgment
before writing shared memory.

## Usefulness

- Verify `brief.md` names the actual project purpose, system shape, and current direction.
- Remove protocol boilerplate from project facts; the manifest and skill already govern MemoryCustodian behavior.
- Compare durable claims with authoritative project files and current code.

## Reachability

- For each active invariant, identify which normal task route loads it.
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

## Scope And Portability

- Separate hard constraints from soft preferences.
- Confirm before storing personal, sensitive, credential-like, or workstation-specific information.
- Prefer an abstract constraint and controlled Evidence reference over raw secrets, contract terms, vendor
  identities, or unnecessary numeric limits.
- Avoid shared absolute machine paths; prefer portable commands, conditional profiles, or user-local configuration.

## Budget

- Keep each decision entry within 120 tokens; preserve the choice and reason, not implementation narration.
- Treat `NEAR LIMIT` (80%–100%) as an immediate dry-run maintenance signal; `OVER BUDGET` requires maintenance.
- Split by area before raising global budgets.
- Run `status` and `check` after maintenance and inspect warnings, not only exit status.
