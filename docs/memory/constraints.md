# Constraints

## MC-CON-20260921-10000001 — Offline core operations

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: security
Evidence:
- repo:pyproject.toml

Constraint:
Core memory operations must work without network access. Skill, plugin, and CLI distribution may use the network.

## MC-CON-20260921-10000002 — Repo-native plain-text storage

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: data-model
Evidence:
- user-confirmed

Constraint:
Store project memory as reviewable Markdown under `docs/`, defaulting to `docs/memory/`; do not introduce RAG, embeddings, vector databases, or cloud memory into the default architecture.

## MC-CON-20260921-10000003 — Cross-agent compatibility

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: compatibility
Evidence:
- repo:adapters

Constraint:
The protocol must remain reusable across Codex, Claude Code, Gemini, and generic agents.

## MC-CON-20260921-10000010 — Transactional multi-file mutation

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: security
Evidence:
- repo:cli/memory_custodian/transactions.py

Constraint:
Multi-file commands must precompute and validate plans, use private crash-recovery journals, and refuse silent partial completion.

## MC-CON-20260921-10000011 — No protocol downgrade

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: version-policy
Evidence:
- repo:cli/memory_custodian/protocol.py

Constraint:
Repair and migration never downgrade a newer project protocol or accept an unparseable protocol version.
