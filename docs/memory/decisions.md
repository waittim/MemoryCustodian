# Decisions

Entries are newest first.

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

## MC-DEC-20260801-07000007 — Protocol 0.7 governance

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: architecture
Evidence:
- user-confirmed
- repo:cli/memory_custodian/local_overlay.py
- test:tests/test_local_snapshot.py
Supersedes: MC-DEC-20260729-ef44900b

Decision:
Use explicit routing and review. Strict reads consume one overlay snapshot; local writes refresh IDs under lock. Defer further governance to 0.8.

Reason:
Avoids mixed-time reads/stale IDs.

## MC-DEC-20260721-3578b077 — Support Python 3.10–3.14

Status: active
Scope: project
Subject: MC-SUBJ-20260801-10000001
Facet: version-policy
Evidence:
- legacy-unverified

Decision:
Support and test Python 3.10 through 3.14.
Reason:
No newer Python feature is required.

## MC-DEC-20260712-53d9eded — Prefer reachable memory

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: behavior
Evidence:
- legacy-unverified

Decision:
Prefer concise, reachable, scope-specific memory over chronology.
Reason:
Reachability determines utility.

## MC-DEC-20260708-ab7efbab — Gemini thin-context support

Status: active
Scope: project
Subject: MC-SUBJ-20260801-30000003
Facet: compatibility
Evidence:
- legacy-unverified

Decision:
Support Gemini through thin `GEMINI.md`, `--with-gemini`, and `./install.sh gemini` skill linking.
Reason:
Avoid eager durable-memory imports.

## MC-DEC-20260705-00552a27 — Targeted active-memory compaction

Status: active
Scope: project
Subject: MC-SUBJ-20260801-40000004
Facet: behavior
Evidence:
- legacy-unverified

Decision:
Provide preview-first `compact --target <file>` with bullet dedupe, reviewed H2 archival, and `status`/`check` guidance.
Reason:
Keep maintenance offline and reviewable.

## MC-DEC-20260704-ddfc2d0c — Claude plugin-root distribution

Status: active
Scope: project
Subject: MC-SUBJ-20260801-50000005
Facet: compatibility
Evidence:
- legacy-unverified

Decision:
Support Claude Code through `.claude-plugin/`, shared skills/bin, `--plugin-dir` tests, and `./install.sh claude`.
Reason:
Provide a verifiable install surface.

## MC-DEC-20260704-342e05b7 — Offline skill evals first

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: behavior
Evidence:
- legacy-unverified

Decision:
Maintain offline skill scenarios and a checker before live-agent evals.
Reason:
Avoid a heavyweight harness.
