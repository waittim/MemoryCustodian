# Decisions

Entries are newest first.

## MC-DEC-20260728-5ea0e265 — Adopt Protocol 0.6 evidence admission and mutation safety.

Status: active
Scope: project
Evidence:
- user-confirmed

Decision:
Adopt Protocol 0.6 evidence admission and mutation safety.

Reason:
Formal memory needs auditable provenance, stable identity, and stale-write rejection.

## MC-DEC-20260721-3578b077 — Target Python 3.10+ minimum version

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Support Python 3.10+ and test the main suite on both Python 3.10 and 3.13.
Reason:
The stdlib-only implementation does not require Python 3.13 features, and the broader range lowers installation friction while retaining a maintained baseline.

## MC-DEC-20260719-59d6d8ed — Keep Protocol 0.5 for v0.9

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Keep the memory protocol at 0.5 while package 0.9 removes CLI semantic guessing and hardens mutation safety.
Reason:
Manifest schema and routing syntax remain compatible with existing 0.5 projects.

## MC-DEC-20260718-491db2c3 — Protocol 0.5

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Keep for v0.8.
Reason:
Existing manifests support strict routing.

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

## MC-DEC-20260704-a4ce76c2 — Add lightweight plugin bootstrap and deterministic packaging

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Add a thin session-start bootstrap and deterministic Codex archive packaging while keeping memory protocol 0.4.
Reason:
Startup should nudge manifest-first loading without injecting full skill text or memory; package versions may advance separately.

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
