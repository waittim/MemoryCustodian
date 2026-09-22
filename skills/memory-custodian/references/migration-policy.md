# Protocol 0.8 Staged Migration Policy

Package 0.12 can read Protocol 0.5, 0.6, and 0.7 projects, including Entry
schema 1 and 2 legacy inputs, while writing only the selected source grammar
until staged migration is complete. Source `protocol_version` and
`entry_schema_version` decide parsing first: schema 1 treats a literal
`memory-custodian-body-v1` string as body text; schema 2/3 decode the explicit
wrapper. A newer or malformed protocol is rejected; migration never silently
downgrades metadata.

Migration has three mutually exclusive stages. Each invocation defaults to a
preview. Applying a preview requires its own `--confirm-plan` and its own
transaction; Prepare and Finalize never share a Plan ID or journal.

```bash
memory-custodian migrate --prepare
memory-custodian migrate --prepare --apply --confirm-plan <PREPARE_PLAN>
memory-custodian migrate --canonicalize
memory-custodian migrate --canonicalize --apply --confirm-plan <CANONICALIZE_PLAN>
memory-custodian migrate --finalize
memory-custodian migrate --finalize --apply --confirm-plan <FINALIZE_PLAN>
```

## Prepare

Prepare records source protocol/schema, project/bootstrap identity, normalized
root, bound local-overlay snapshot, and source digests in protected
repo-external migration state. It leaves shared protocol metadata unchanged.
It may perform only mechanically provable transformations and emits a
per-entry checklist for Evidence, Subject, Facet, relations, and
canonicalization blockers. It never invents Evidence, Subject equivalence,
Facet assignments, exceptions, or reconciliations.

## Manual interval and canonicalize

Canonicalize is repeatable and preview-first. It may convert an unambiguous
legacy unit but requires explicit type, title, Evidence, Scope, Subject, and
Facet for semantic promotion. Ambiguous units remain unchanged and block
apply. Target-only Entry schema 3 metadata is held in protected migration
state until Finalize; a bound local overlay uses the shared Entry schema and
participates in the same eventual transition.

## Finalize

Finalize creates a fresh Plan ID and transaction, revalidates the prepare
binding and current source files, requires canonical active entries, complete
Subject/Facet/relations, and no audit ERROR/BLOCKER or canonicalization
blocker. It writes target-only schema 3 rewrites and bound local rewrites in
one transaction, commits `protocol_version: 0.8` and `entry_schema_version: 3`
last, then removes migration state. A failure is detected by the transaction
audit and is completed or rolled back only through the recovery policy.

Migration is syntax-aware and deterministic; it does not infer semantics from
timestamps, file order, prose similarity, or Evidence counts, and it is not a
promise of semantic correctness.
