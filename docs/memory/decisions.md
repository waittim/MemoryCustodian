# Decisions

Entries are newest first.

## MC-DEC-20260827-8f4c2a91 — Protocol 0.7 body fencing

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: compatibility
Evidence:
- repo:cli/memory_custodian/entries.py
- repo:cli/memory_custodian/forget.py
- test:tests/test_protocol_07_release_gaps.py
- doc:skills/memory-custodian/references/memory-file-protocol.md

Decision:
`memory-custodian-body-v1` fence; legacy entity ordinary. Selectors/search semantic display text; mutation/storage raw source.

Reason:
Versioned delimiters preserve semantics.

## MC-DEC-20260801-07000007 — Adopt Protocol 0.7 deterministic governance

Status: active
Scope: project
Subject: MC-SUBJ-20260729-7e5c3a91
Facet: architecture
Evidence:
- user-confirmed
Supersedes: MC-DEC-20260729-ef44900b

Decision:
Use one mutation guard, explicit task/scope routing, structural conflict review, and bound local overlays; defer complex governance apply to Protocol 0.8 transactions.

Reason:
This keeps selection and reconciliation deterministic without partial multi-file governance writes.

## MC-DEC-20260721-3578b077 — Target Python 3.10+ minimum version

Status: active
Scope: project
Subject: MC-SUBJ-20260801-10000001
Facet: version-policy
Evidence:
- legacy-unverified

Decision:
Support Python 3.10+ and test every supported minor from Python 3.10 through 3.14.
Reason:
The stdlib-only CLI needs no newer-minor feature, and full minor coverage keeps the open-ended range honest.

## MC-DEC-20260712-53d9eded — Prioritize useful and reachable memory over chronological accumulation.

Status: active
Scope: project
Subject: MC-SUBJ-20260801-20000002
Facet: behavior
Evidence:
- legacy-unverified

Decision:
Prioritize useful and reachable memory over chronological accumulation; keep each decision concise and scope-specific.
Reason:
Structural validity alone does not make memory reachable or useful.

## MC-DEC-20260708-ab7efbab — Support Gemini through thin context and Agent Skills

Status: active
Scope: project
Subject: MC-SUBJ-20260801-30000003
Facet: compatibility
Evidence:
- legacy-unverified

Decision:
Support Gemini with thin `GEMINI.md` bootstrap snippets, `--with-gemini`, and `./install.sh gemini` linking the skill into Gemini's skills directory.
Reason:
Gemini context imports are eager, so durable memory stays manifest-routed.

## MC-DEC-20260705-00552a27 — Add target compaction for active memory budgets

Status: active
Scope: project
Subject: MC-SUBJ-20260801-40000004
Facet: behavior
Evidence:
- legacy-unverified

Decision:
Add `compact --target <file>` for over-budget active files. It dry-runs by default, dedupes simple bullet files, archives old complete H2 entries for decisions/changelog, and has `status`/`check` suggest the command.
Reason:
Budget failures need an offline reviewable maintenance path.

## MC-DEC-20260704-ddfc2d0c — Treat Claude as a plugin-root distribution target

Status: active
Scope: project
Subject: MC-SUBJ-20260801-50000005
Facet: compatibility
Evidence:
- legacy-unverified

Decision:
Support Claude Code through `.claude-plugin/`, `skills/`, `bin/`, local `--plugin-dir` testing, and `./install.sh claude`.
Reason:
Claude needs a verifiable plugin-root install surface.

## MC-DEC-20260704-342e05b7 — Add deterministic skill evals first

Status: active
Scope: project
Subject: MC-SUBJ-20260801-60000006
Facet: behavior
Evidence:
- legacy-unverified

Decision:
Maintain offline skill eval scenarios and a checker before live agent eval infrastructure.
Reason:
Guard behavior offline without a heavyweight harness.
