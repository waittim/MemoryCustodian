# Memory Manifest

MemoryCustodian uses this file to decide which local project memory files should be loaded for a task.

## Always load
- brief.md

## Load by task

### Planning / architecture / refactoring
Use when the agent is making structural decisions, comparing approaches, writing a plan, or changing project direction.
Load:
- decisions.md
- constraints.md
- do-not-use.md

### Implementation / execution
Use when the agent is writing code, editing files, implementing a plan, debugging, or performing concrete project work.
Load:
- constraints.md
- do-not-use.md
Load if present:
- preferences.md

### User-facing artifact generation
Use when the agent produces text that may be copied, published, submitted, committed, sent, or shown to others.
Load if present:
- rules/output.md
- preferences.md
Also load:
- do-not-use.md

### User or project preferences
Use when the task depends on style, workflow, conventions, or recurring user preferences.
Load if present:
- preferences.md

### Change history / project recap
Use when the user asks what changed, what was decided, or how the project evolved.
Load:
- decisions.md
Load if present:
- changelog.md

### Memory maintenance
Use when adding, compacting, editing, deleting, or auditing memory.
Load:
- inbox.md
- do-not-use.md
Load if present:
- changelog.md

## Optional profiles
Load profile files only when the current task clearly matches that workflow or the user explicitly requests it.
Examples:
- profiles/git.md
- profiles/docs.md
- profiles/release.md
- profiles/tickets.md
- profiles/research.md

## Area-specific memory
Load area files only when the current task clearly touches that area.
Examples:
- areas/frontend.md
- areas/backend.md
- areas/infra.md

## Explicit only
Do not load these unless the user explicitly asks or the task is memory maintenance:
- archive/

## Context budget
- brief.md: 500 tokens max
- decisions.md: 800 tokens max
- constraints.md: 400 tokens max
- do-not-use.md: 400 tokens max
- preferences.md: 300 tokens max, if present
- rules/*.md: 400 tokens max per file, if present
- profiles/*.md: 500 tokens max per file, if present
- areas/*.md: 600 tokens max per file, if present
- changelog.md: 800 tokens max, if present
- inbox.md: memory maintenance only
- archive/: explicit only
