# Claude Code Adapter Install

The adapter targets MemoryCustodian 0.12 / Protocol 0.8. Keep the generated
`CLAUDE.md` thin; the Skill references are the normative source for routing,
transaction recovery, audit/JSON, staged migration, and ErasureScope.

## Test The Plugin

From this repository, test MemoryCustodian as a Claude Code plugin:

```bash
claude --plugin-dir .
```

Directly invoke the plugin skill with:

```text
/memory-custodian:memory-custodian
```

Claude Code plugin skills are namespaced by plugin name to avoid collisions.

## Install The Plugin

From this repository, install MemoryCustodian into Claude Code's personal skills directory:

```bash
./install.sh claude
```

This creates a symlink at `${CLAUDE_HOME:-$HOME/.claude}/skills/memory-custodian` pointing to this plugin root. The plugin root contains `.claude-plugin/plugin.json`, `skills/memory-custodian/SKILL.md`, and `bin/memory-custodian`.

## Bootstrap A Project

Use the CLI if it is available:

```bash
memory-custodian init --project-root <project> --with-claude
```

Or add the contents of `CLAUDE.snippet.md` to the target project's `CLAUDE.md`.

Optionally copy files from `commands/` into the project's `.claude/commands/` directory.

Keep `CLAUDE.md` as an entry point. Store durable memory in `docs/memory/`.

For automation, use `memory-custodian audit --format json`; an interrupted
write is handled through `audit --transactions` and opaque-ID `recover`.
