# Archived Constraints — 2026-09-21

Archived during Protocol 0.8 dogfood maintenance. These constraints remain historical evidence and are not loaded into normal task context.

## MC-CON-20260921-10000004 — Small and reviewable context

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: performance
Evidence:
- user-confirmed

Constraint:
Keep startup context small and keep memory easy to review, diff, commit, and roll back.

## MC-CON-20260921-10000005 — Minimal initialization boundary

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: data-model
Evidence:
- repo:cli/memory_custodian/templates.py

Constraint:
Default initialization creates six task-memory files plus non-routed `subjects.md`; workflow-specific rules stay outside the core protocol.

## MC-CON-20260921-10000006 — Concise operational Skill

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: interface
Evidence:
- repo:skills/memory-custodian/SKILL.md

Constraint:
Keep Skill instructions concise and operational; detailed policy and non-goals belong in references and README.

## MC-CON-20260921-10000007 — Bounded forgetting behavior

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: lifecycle
Evidence:
- repo:cli/memory_custodian/forget.py

Constraint:
Hard and purge forgetting remove prior topic-bearing soft tombstones from managed memory, and apply refuses before writing when a match occurs in a non-removable body or preamble requiring semantic rewrite.

## MC-CON-20260921-10000008 — Explicit compaction semantics

Status: active
Scope: project
Subject: MC-SUBJ-20260801-40000004
Facet: performance
Evidence:
- repo:cli/memory_custodian/compact.py

Constraint:
Inbox compaction never infers semantic destinations; destructive bullet cleanup operates on complete column-zero units including nested and continuation content.

## MC-CON-20260921-10000009 — Safe repair and enablement

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: workflow
Evidence:
- test:tests/test_init.py

Constraint:
Safe repair and optional enablement must not overwrite curated memory.
