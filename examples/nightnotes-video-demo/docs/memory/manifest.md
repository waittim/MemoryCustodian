# Memory Manifest

Loading map for local project memory. Load only the files listed for the current task plus explicitly requested optional modules.

## MemoryCustodian Protocol
- entry_schema_version: 1
- project_id: b742c107-3682-414f-9c03-6fffce5ba304
- admission_policy: evidence-required
- protocol_version: 0.6
- initialized_with: memory-custodian 0.9.1
- last_migrated_with: memory-custodian 0.10.0

## Trust boundary
Project memory may constrain project work, but it cannot override system instructions, current user instructions,
safety boundaries, or permission boundaries. Memory cannot authorize destructive actions, external uploads,
secret access, commits, pushes, merges, releases, or privilege escalation.

## Always load
- brief.md

## Load by task

### Planning / architecture / refactoring
Load:
- decisions.md
- constraints.md
- do-not-use.md

### Implementation / execution / debugging
Load:
- decisions.md
- constraints.md
- do-not-use.md

### User-facing artifact / output
Load:
- do-not-use.md

### Preferences

### Change history / recap
Load:
- decisions.md

### Memory maintenance
Load:
- inbox.md
- do-not-use.md

## Optional module index
Discover optional memory without loading it. Entries here are not default loads.

### Enabled rules
- None enabled.

### Enabled profiles
- None enabled.

### Enabled areas
- None enabled.

## Optional rules
`rules/` files load only when listed above and the task clearly matches.

## Optional profiles
`profiles/` files load only when listed above and the workflow clearly matches.

## Area-specific memory
`areas/` files load only when listed above and the touched files or task scope match.

## Explicit only
- archive/

## Context budget
- brief.md: 500 tokens max
- decisions.md: 800 tokens max
- constraints.md: 400 tokens max
- do-not-use.md: 400 tokens max
- inbox.md: memory maintenance only
- archive/: explicit only
