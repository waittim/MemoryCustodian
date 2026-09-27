# Decisions

Entries are newest first.

## MC-DEC-20260921-40000001 — Protocol 0.8 reliability governance

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: architecture
Evidence:
- user-confirmed
- doc:docs/MemoryCustodian-plan-0.12.0-erasure-aligned-revised.md
Supersedes: MC-DEC-20260801-07000007

Decision:
Use Protocol 0.8 for transactional recovery, unified audit/output, staged migration, and bounded erasure before 1.0.

Reason:
Adds recovery without overstating erasure.

## MC-DEC-20260827-8f4c2a91 — Protocol 0.7 body fencing

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: compatibility
Evidence:
- repo:cli/memory_custodian/entries.py
- test:tests/test_protocol_07_release_gaps.py

Decision:
Use `memory-custodian-body-v1`; treat legacy entities literally. Search decoded text; mutate raw source.

Reason:
Preserves parse/write semantics.

## MC-DEC-20260721-3578b077 — Support Python 3.10–3.14

Status: active
Scope: project
Subject: MC-SUBJ-20260801-10000001
Facet: version-policy
Evidence:
- repo:.github/workflows/ci.yml

Decision:
Support Python 3.10–3.14.

Reason:
CI tests this range.

## MC-DEC-20260712-53d9eded — Prefer reachable memory

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: behavior
Evidence:
- doc:README.md

Decision:
Prefer concise, scoped memory reachable through normal task routes.

Reason:
Route access gives it utility.

## MC-DEC-20260708-ab7efbab — Gemini thin-context support

Status: active
Scope: project
Subject: MC-SUBJ-20260801-30000003
Facet: compatibility
Evidence:
- doc:adapters/gemini/install.md

Decision:
Support Gemini with a thin bootstrap, init --with-gemini, and skill install.

Reason:
Avoid eager memory imports.

## MC-DEC-20260705-00552a27 — Targeted active-memory compaction

Status: active
Scope: project
Subject: MC-SUBJ-20260801-40000004
Facet: behavior
Evidence:
- test:tests/test_add_forget_compact.py
- repo:skills/memory-custodian/references/compaction-policy.md

Decision:
Use preview-first compact --target; review exact dedupe and H2 archival, then run status/check.

Reason:
Keep maintenance offline and reviewable.

## MC-DEC-20260704-ddfc2d0c — Claude plugin-root distribution

Status: active
Scope: project
Subject: MC-SUBJ-20260801-50000005
Facet: compatibility
Evidence:
- test:tests/test_plugin_package.py

Decision:
Support Claude via .claude-plugin/, shared skills/bin, and install.sh claude.

Reason:
Keeps install verifiable.

## MC-DEC-20260704-342e05b7 — Offline skill evals first

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: behavior
Evidence:
- repo:scripts/check-skill-evals.py

Decision:
Run offline skill scenarios and a checker before live-agent evals.

Reason:
Avoid heavyweight tools.
