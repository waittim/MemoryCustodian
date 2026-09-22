# Codex Adapter Install

The adapter targets MemoryCustodian 0.12 / Protocol 0.8. The snippet is a
thin entry point; the installed Skill and its references define routing,
transaction recovery, audit/JSON, staged migration, and ErasureScope.

1. Install the skill by copying or symlinking `skills/memory-custodian` into the Codex skills directory.
2. Add the contents of `AGENTS.snippet.md` to the target project's `AGENTS.md`.
3. Run `memory-custodian init --project-root <project> --with-codex` if the CLI is installed.

Keep `AGENTS.md` short. The project memory belongs in `docs/memory/`.

For a machine-readable health result use `memory-custodian audit --format
json`. If a mutation is interrupted, inspect `audit --transactions` and use
the opaque transaction ID with `recover`; do not load private journal backups.
