# Decisions

## 2026-06-30 - Use plain text memory files
Decision:
Store project memory as markdown files inside each project.

Reason:
This keeps memory local, inspectable, portable, and easy to version with git.

## 2026-06-30 - Default to docs/memory
Decision:
Use `docs/memory/` as the default managed memory directory.

Reason:
A visible docs directory is easier to review, diff, commit, and share across agents than a hidden directory.

## 2026-06-30 - Keep agent entry files small
Decision:
Use `AGENTS.md`, `CLAUDE.md`, and similar files only as entry points.

Reason:
The full memory belongs in dedicated memory files to avoid context bloat.

## 2026-06-30 - Implement the CLI with Python stdlib
Decision:
Build the MVP CLI with Python standard library modules only.

Reason:
This keeps installation simple and works without network access.

## 2026-07-02 - Adopt minimal-first v0.3 protocol
Decision:
Default initialization should create only the six core memory files: `manifest.md`, `brief.md`, `decisions.md`, `constraints.md`, `do-not-use.md`, and `inbox.md`.

Reason:
Small projects should not receive optional workflow files until they are useful. Optional memory belongs behind explicit enablement.

Implications:
- `preferences.md`, `changelog.md`, `rules/`, `profiles/`, `areas/`, and `archive/` are optional.
- `manifest.md` is the loading source of truth.
- CLI support includes `enable` and `check`.

Status:
active
