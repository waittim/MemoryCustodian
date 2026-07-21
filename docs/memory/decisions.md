# Decisions

Entries are newest first.

## 2026-07-20 - Target Python 3.13+ minimum version
Decision:
Update project Python version requirement to `>=3.13` across `pyproject.toml`, CI matrix, and documentation.
Reason:
Keep runtime requirements aligned with current stable Python major releases and modern stdlib features.

## 2026-07-19 - Keep Protocol 0.5 for v0.9
Decision:
Keep the memory protocol at 0.5 while package 0.9 removes CLI semantic guessing and hardens mutation safety.
Reason:
Manifest schema and routing syntax remain compatible with existing 0.5 projects.

## 2026-07-18 - Protocol 0.5
Decision:
Keep for v0.8.
Reason:
Existing manifests support strict routing.

## 2026-07-12 - Prioritize useful and reachable memory over chronological accumulation.
Decision:
Prioritize useful and reachable memory over chronological accumulation; keep each decision concise and scope-specific.
Reason:
Production use showed that a generic brief, root-only subsystem decisions, and age-only archival can pass structural checks while failing to provide relevant context.

## 2026-07-08 - Support Gemini through thin context and Agent Skills
Decision:
Support Gemini with thin `GEMINI.md` bootstrap snippets, `--with-gemini`, and `./install.sh gemini` linking the skill into Gemini's skills directory.
Reason:
Gemini context files are loaded into prompt context, so project memory must remain manifest-driven while skill installation provides full protocol behavior.

## 2026-07-05 - Add target compaction for active memory budgets
Decision:
Add `compact --target <file>` for over-budget active files. It dry-runs by default, dedupes simple bullet files, archives old complete H2 entries for decisions/changelog, and has `status`/`check` suggest the command.
Reason:
Agents need an offline, reviewable path from budget failure to safe maintenance. Semantic rewrites still require review.

## 2026-07-04 - Add lightweight plugin bootstrap and deterministic packaging
Decision:
Add a thin session-start bootstrap and deterministic Codex archive packaging while keeping memory protocol 0.4.
Reason:
Startup should nudge manifest-first loading without injecting full skill text or memory; package versions may advance separately.

## 2026-07-04 - Treat Claude as a plugin-root distribution target
Decision:
Support Claude Code through `.claude-plugin/`, `skills/`, `bin/`, local `--plugin-dir` testing, and `./install.sh claude`.
Reason:
Claude support needs a verifiable plugin-root install surface.

## 2026-07-04 - Add deterministic skill evals first
Decision:
Maintain offline skill eval scenarios and a checker before live agent eval infrastructure.
Reason:
Guard the behavior contract without services, non-stdlib dependencies, or heavyweight harnesses.

## 2026-07-04 - Use project-memory card branding
Decision:
Use stacked index-card branding with a near-black background and short blue bookmark marker.
Reason:
Signal local project memory and manifest-driven retrieval, not CI validation.

## 2026-07-04 - Make plugin distribution self-contained
Decision:
Codex plugin support includes repo-local marketplace metadata, plugin metadata/assets, and a bundled CLI wrapper. Project memory stays in `docs/memory/`.
Reason:
Plugin install should expose the workflow and helper CLI without copying project memory.

## 2026-07-03 - Version package and memory protocol separately
Decision:
Track package/plugin version separately from memory protocol version. Manifests record protocol metadata.
Reason:
CLI or skill updates must not silently mutate existing project memory.

## 2026-07-03 - Separate offline memory from distribution
Decision:
Memory operations work offline by default; installation/update flows may use network distribution.
Reason:
Runtime memory stays local-first while updates can use marketplaces, package managers, or git.
