# Archived Decisions — 2026-08-01

These superseded governance entries remain historical and are not part of normal context routing.

## MC-DEC-20260729-ef44900b — Use one mutation guard and separate private execution plans from public

Status: superseded
Superseded-By: MC-DEC-20260801-07000007
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: architecture
Evidence:
- user-confirmed
Supersedes: MC-DEC-20260728-5ea0e265

Decision:
Use one mutation guard and separate private execution plans from public previews.

Reason:
A single bootstrap-to-project lock handoff prevents identity races across every writer; private state permissions and redacted public plans preserve concurrency and erasure boundaries.

## MC-DEC-20260728-5ea0e265 — Adopt Protocol 0.6 evidence admission and mutation safety.

Status: superseded
Superseded-By: MC-DEC-20260729-ef44900b
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: architecture
Evidence:
- user-confirmed

Decision:
Use Protocol 0.6 evidence admission, stable Subject/Facet conflict identity, explicit erasure boundaries,
repo-external preview seeds, lock-time plan rebuilds, and deterministic budget states.

Reason:
This keeps provenance, ownership, forgetting scope, and stale-write rejection deterministic and reviewable.
