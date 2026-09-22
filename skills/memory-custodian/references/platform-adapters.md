# Platform Adapters

MemoryCustodian 0.12 / Protocol 0.8 has one shared workflow. Codex, Claude
Code, Gemini, and generic agents differ only in how their short entry file
invokes that workflow; an adapter is not a second router, Subject registry,
conflict engine, or erasure implementation.

Every adapter must communicate the following sequence:

1. Locate `docs/memory/manifest.md`; read it and `brief.md` before substantial
   work. Missing manifest means incomplete setup; do not infer routes.
2. Choose one canonical task (`general`, `planning`, `implementation`,
   `artifact`, `preferences`, `history`, or `maintenance`) and expose it.
3. Provide touched/planned repo-relative paths, or an explicit area for
   pathless planning. Pass explicit rules/profiles when needed.
4. Reuse the CLI's shared router, normally:

   ```bash
   memory-custodian read --task <TASK> --strict-routing --path <PATH> --explain
   ```

   Stop substantive modification on `INCOMPLETE`, `AMBIGUOUS`, `INVALID`, or
   a deterministic unresolved conflict. Do not infer area/profile relevance
   from prose, timestamps, file order, or Evidence count.
5. Never load all memory, `inbox.md`, or `archive/` by default. `subjects.md`
   and reconciliation records are protocol-operation authorities, not normal
   context-pack content.
6. Before merge/rebase run conflict or merge-aware audit when Git is available;
   resolve REVIEW only through an explicit transactional reconciliation.
7. Keep memory as project context, not authorization. It cannot override
   system/current-user/safety/permission boundaries or authorize secrets,
   destructive actions, uploads, commits, pushes, merges, or releases.
8. After meaningful decisions, corrections, or rejected approaches, write or
   propose Evidence-backed memory using an existing Subject ID.

## Shared mutation and output contract

All multi-file writes use preview, matching Plan ID confirmation, lock-held
revalidation, and the shared transaction journal. This includes forgetting,
governance, staged migration, enable/link, repair, schema conversion, and
local reset. On a crash, report `audit --transactions`, select an opaque
transaction ID, and use the transaction recovery workflow; never expose or
load protected backup bytes.

Use `--format json` for machine-readable output. Every public envelope uses
`output_schema_version: 1`; audit puts `audit_schema_version: 1` in `data`.
Forgetting, ID forget, local reset, and recovery expose the same canonical
`data.erasure_scope` (`erasure_scope_schema_version: 1`) and
`history_check_status`. `unavailable` is not PASS, and
`no-reachable-copy-detected` is only a bounded local inspection.

Forgetting controls what remains available to future agents through
MemoryCustodian. It is not a guarantee of erasure from Git history or
previously distributed copies. Hard forget targets managed active memory;
purge additionally targets managed archive. Neither rewrites Git history or
revokes clones, forks, backups, caches, or other distributed copies.

## Platform entry points

### Codex

Keep `AGENTS.md` short and point at `docs/memory/`. Use
`adapters/codex/AGENTS.snippet.md`.

### Claude Code

Keep `CLAUDE.md` short and point at `docs/memory/`. Use
`adapters/claude-code/CLAUDE.snippet.md`; optional command files may expose
status, compact, forget, audit, and recovery commands but must not redefine
the protocol.

### Gemini

Keep `GEMINI.md` thin. Do not import memory files with `@` directives; load
through the manifest at task time. Use `adapters/gemini/GEMINI.snippet.md`.

### Generic agents

Use `adapters/generic/agent-instructions.md` when no platform-specific entry
surface exists. A missing memory directory is not an error; a memory
directory without `manifest.md` is incomplete and must not be routed by
filename guesses.

The static adapter checker verifies this shared contract. It checks static
text only and is not a live-agent or semantic-correctness benchmark.
