# Decisions

Entries are newest first.

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

## 2026-07-02 - Keep Skill instructions operational and concise
Decision:
Keep `SKILL.md` focused on agent execution; put detailed policy in references, README, or memory files.
Reason:
`SKILL.md` is an execution entry point, not a positioning document.

## 2026-07-02 - Keep the core protocol minimal
Decision:
Default initialization creates only `manifest.md`, `brief.md`, `decisions.md`, `constraints.md`, `do-not-use.md`, and `inbox.md`.
Reason:
Small projects should not receive optional memory until needed.

## 2026-06-30 - Use local text memory
Decision:
Store durable project memory as Markdown under `docs/`, defaulting to `docs/memory/`; keep agent entry files thin.
Reason:
Memory should be local, inspectable, portable, diffable, and easy to roll back.
