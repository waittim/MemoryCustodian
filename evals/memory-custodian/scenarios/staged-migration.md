# Staged Migration Contract

## Purpose

Verify safe migration into Protocol 0.8 / Entry schema 3 without semantic
guessing or protocol downgrade.

## Setup

Use a readable Protocol 0.5, 0.6, or 0.7/schema 1 or 2 project, optionally
with a bound local overlay and a literal schema-1 body fence.

## Prompt

Run `migrate --prepare`, review the manual checklist, canonicalize explicit
units, and finalize only after the audit is clear.

## Required Observations

- Prepare, canonicalize, and finalize are mutually exclusive stages with
  distinct Plan IDs and transactions.
- Source metadata selects the parser; schema-1 wrapper-like text stays
  literal, and ambiguous units remain unchanged and block apply.
- Prepare leaves shared protocol metadata unchanged; finalize writes Protocol
  0.8 / Entry schema 3 metadata last in one transaction with bound local
  rewrites.
- A newer or malformed protocol is rejected instead of silently downgraded.

## Forbidden Outcomes

- Inferring Subject, Facet, Evidence, or semantic equivalence from prose,
  timestamps, file order, or Evidence counts.
- Reusing a Prepare Plan ID or transaction for Finalize.
- Writing target-only schema 3 metadata into a source-schema file before the
  final transition.

## Passing Criteria

Migration is staged, reviewable, crash-recoverable, and only finalizes after
canonicalization blockers and audit ERROR/BLOCKER findings are cleared.
