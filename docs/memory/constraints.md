# Constraints

## MC-CON-20261110-b07a3269 — Benchmark evidence

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: adoption-policy
Evidence:
- doc:RELEASE-NOTES.md

Constraint:
General effectiveness claims require held-out live evidence.

## MC-CON-20260921-10000001 — Offline

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: security
Evidence:
- repo:pyproject.toml

Constraint:
Core stays offline; distribution may use networks.

## MC-CON-20260921-10000002 — Storage

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: data-model
Evidence:
- user-confirmed

Constraint:
Keep Markdown under docs/memory/; exclude RAG, vector DBs, cloud memory.

## MC-CON-20260921-10000003 — Compatibility

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: compatibility
Evidence:
- repo:adapters

Constraint:
Support Codex, Claude Code, Gemini, generic agents.

## MC-CON-20260921-10000010 — Transactions

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: security
Evidence:
- repo:cli/memory_custodian/transactions.py

Constraint:
Journal multi-file writes; verify terminal effects before cleanup.

## MC-CON-20260921-10000011 — Versions

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: version-policy
Evidence:
- repo:cli/memory_custodian/protocol.py

Constraint:
Repair/migration reject malformed versions and never downgrade.
