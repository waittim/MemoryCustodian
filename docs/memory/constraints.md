# Constraints

## MC-CON-20261110-b07a3269 — Do not claim MemoryCustodian improves task success, reliability, or toke

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: adoption-policy
Evidence:
- user-confirmed
- doc:RELEASE-NOTES.md
- doc:docs/evaluations/benchmark/README.md
- repo:scripts/run-memory-bench.py

Constraint:
Do not claim MemoryCustodian improves task success, reliability, or token efficiency until real headless runtime comparisons are run across the benchmark conditions; v0.13.0 provides only offline harness and parity infrastructure, and --mode live returns BLOCKER until a live runtime adapter is configured.

## MC-CON-20260921-10000001 — Offline core operations

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: security
Evidence:
- repo:pyproject.toml

Constraint:
Core memory operations must be network-independent; distribution may use the network.

## MC-CON-20260921-10000002 — Repo-native plain-text storage

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: data-model
Evidence:
- user-confirmed

Constraint:
Keep project memory as reviewable Markdown under docs/, defaulting to docs/memory/; keep RAG, embeddings, vector databases, and cloud memory out of the default architecture.

## MC-CON-20260921-10000003 — Cross-agent compatibility

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: compatibility
Evidence:
- repo:adapters

Constraint:
Keep the protocol reusable across Codex, Claude Code, Gemini, and generic agents.

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
Repair and migration never downgrade newer protocols or accept malformed versions.
