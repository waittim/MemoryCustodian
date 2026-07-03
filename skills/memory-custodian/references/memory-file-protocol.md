# Memory File Protocol

## Default Location

Use `docs/memory/` by default. Hidden `.memory/` directories are allowed for projects that explicitly choose them, but visible `docs/memory/` is preferred for review, diffs, and team workflows.

## Core Files

```text
docs/memory/
  manifest.md
  brief.md
  decisions.md
  constraints.md
  do-not-use.md
  inbox.md
```

These six files are the core protocol. They are enough for minimal mode.

## Non-Goals

MemoryCustodian does not provide:

- RAG retrieval
- embedding-based search
- vector database storage
- cloud-hosted memory
- opaque platform-specific memory stores
- chat log archiving
- a background daemon
- automatic full-context loading

## Optional Files

Create these only when the project needs them:

```text
docs/memory/
  preferences.md
  changelog.md
  rules/
    output.md
    code-style.md
    safety.md
    review.md
  profiles/
    git.md
    docs.md
    release.md
    tickets.md
    research.md
  areas/
    frontend.md
    backend.md
    infra.md
  archive/
```

## Loading Levels

Level 1 default:

- `brief.md`

Level 2 task-specific:

- `decisions.md`
- `constraints.md`
- `do-not-use.md`
- `preferences.md`, if present and relevant
- `rules/*.md`, if present and relevant
- `profiles/*.md`, if present and relevant
- `areas/*.md`, if present and relevant

Level 3 maintenance or explicit request:

- `inbox.md`
- `changelog.md`, if present

Level 4 explicit request only:

- `archive/`

## Context Budgets

Recommended maximums:

- `brief.md`: 500 tokens
- `decisions.md`: 800 tokens
- `constraints.md`: 400 tokens
- `preferences.md`: 300 tokens
- `do-not-use.md`: 400 tokens
- `rules/*.md`: 400 tokens per file
- `profiles/*.md`: 500 tokens per file
- `areas/*.md`: 600 tokens per file
- `changelog.md`: 800 tokens
- `inbox.md`: no default load; compact when it grows beyond 30 items
- `archive/`: explicit only

## File Responsibilities

### manifest.md

Defines how agents should load memory, which files are default, and which files are conditional.

### brief.md

The only default memory file. Keep it short, current, and focused on the active project direction.

### decisions.md

Confirmed decisions with date, decision, and reason. Do not store brainstorming as decisions.

### constraints.md

Hard requirements. These should be treated as stronger than preferences.

### preferences.md

Optional soft user or project preferences. These guide choices but can be overridden by explicit user requests.

### do-not-use.md

Rejected options, known failed paths, and tombstones. Agents should check it before reintroducing approaches.

### inbox.md

Temporary holding area for memory candidates that need review or compaction.

### changelog.md

Optional memory maintenance log. Keep it factual and brief.

### rules/

Optional task-specific rules. Load a rule file only when the current task clearly matches it.

### profiles/

Optional workflow-specific rules. Keep Git, release, ticket, docs, and research workflows out of the core protocol.

### areas/

Optional area-specific memory for monorepos or large projects. Load area files only when the task touches that area.

### archive/

Long-lived raw or old material. Do not load by default.
