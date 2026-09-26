# Archived Memory: decisions.md

Complete historical entries moved from active memory after reviewed compaction.
This file is explicit-only and is not part of normal task context.

## MC-DEC-20260801-07000007 — Protocol 0.7 governance

Status: superseded
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: architecture
Evidence:
- user-confirmed
- repo:cli/memory_custodian/local_overlay.py
- test:tests/test_local_snapshot.py
Supersedes: MC-DEC-20260729-ef44900b
Superseded-By: MC-DEC-20260921-40000001

Decision:
Use explicit routing and review. Strict reads consume one overlay snapshot; local writes refresh IDs under lock. Defer further governance to 0.8.

Reason:
Avoids mixed-time reads/stale IDs.
