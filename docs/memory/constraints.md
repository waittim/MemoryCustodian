# Constraints

## MC-CON-20261110-b07a3269 — No premature benchmark claims

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: adoption-policy
Evidence:
- doc:RELEASE-NOTES.md

Constraint:
Do not claim task gains until live runs complete; v0.13.0 is offline parity only.

## MC-CON-20260921-10000001 — Offline core operations

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: security
Evidence:
- repo:pyproject.toml

Constraint:
Core operations are network-independent; distribution may use network.

## MC-CON-20260921-10000002 — Repo-native plain-text storage

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: data-model
Evidence:
- user-confirmed

Constraint:
Store memory as Markdown in docs/memory/; keep RAG, vector DBs, and cloud memory out.

## MC-CON-20260921-10000003 — Cross-agent compatibility

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: compatibility
Evidence:
- repo:adapters

Constraint:
Keep protocol reusable across Codex, Claude Code, Gemini, and generic agents.

## MC-CON-20260921-10000010 — Transactional multi-file mutation

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: security
Evidence:
- repo:cli/memory_custodian/transactions.py

Constraint:
Journal multi-file changes and verify terminal effects before cleanup.

## MC-CON-20260921-10000011 — No protocol downgrade

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: version-policy
Evidence:
- repo:cli/memory_custodian/protocol.py

Constraint:
Repair and migration never downgrade protocols or accept malformed versions.
