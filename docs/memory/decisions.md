# Decisions

Entries are newest first.

## MC-DEC-20260728-5ea0e265 — Adopt Protocol 0.6 evidence admission and mutation safety.

Status: active
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

## MC-DEC-20260721-3578b077 — Target Python 3.10+ minimum version

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Support Python 3.10+ and test the main suite on both Python 3.10 and 3.13.
Reason:
The stdlib-only implementation does not require Python 3.13 features, and the broader range lowers installation friction while retaining a maintained baseline.

## MC-DEC-20260712-53d9eded — Prioritize useful and reachable memory over chronological accumulation.

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Prioritize useful and reachable memory over chronological accumulation; keep each decision concise and scope-specific.
Reason:
Production use showed that a generic brief, root-only subsystem decisions, and age-only archival can pass structural checks while failing to provide relevant context.

## MC-DEC-20260708-ab7efbab — Support Gemini through thin context and Agent Skills

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Support Gemini with thin `GEMINI.md` bootstrap snippets, `--with-gemini`, and `./install.sh gemini` linking the skill into Gemini's skills directory.
Reason:
Gemini context files are loaded into prompt context, so project memory must remain manifest-driven while skill installation provides full protocol behavior.

## MC-DEC-20260705-00552a27 — Add target compaction for active memory budgets

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Add `compact --target <file>` for over-budget active files. It dry-runs by default, dedupes simple bullet files, archives old complete H2 entries for decisions/changelog, and has `status`/`check` suggest the command.
Reason:
Agents need an offline, reviewable path from budget failure to safe maintenance. Semantic rewrites still require review.

## MC-DEC-20260704-ddfc2d0c — Treat Claude as a plugin-root distribution target

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Support Claude Code through `.claude-plugin/`, `skills/`, `bin/`, local `--plugin-dir` testing, and `./install.sh claude`.
Reason:
Claude support needs a verifiable plugin-root install surface.

## MC-DEC-20260704-342e05b7 — Add deterministic skill evals first

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Maintain offline skill eval scenarios and a checker before live agent eval infrastructure.
Reason:
Guard the behavior contract without services, non-stdlib dependencies, or heavyweight harnesses.
