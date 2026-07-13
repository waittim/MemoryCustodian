# Memory File Protocol

## Default Location

Use `docs/memory/` by default. Custom memory directories, if used, must still live under `docs/` so project memory remains visible, reviewable, and easy to diff in team workflows.

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
- each decision entry: 120 tokens recommended maximum, including title, decision, and reason
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

Defines how agents should load memory, which files are default, and which files are conditional. It should include MemoryCustodian Protocol metadata with `protocol_version`, `initialized_with`, and `last_migrated_with` fields. It should also include a lightweight optional module index for enabled `rules/`, `profiles/`, and `areas/` files so agents can discover them without loading their contents.

### brief.md

The only default memory file. Keep it short, current, and focused on project purpose, system shape, and active direction. A generated TODO or protocol description is not a valid project brief.

### decisions.md

Cross-cutting confirmed decisions with date, decision, and reason. Keep each entry within 120 tokens: one or two sentences for the choice and one sentence for the reason. Move supporting implementation detail elsewhere. Do not store brainstorming or subsystem-only choices here. Update or supersede older entries when the decision changes.

### constraints.md

Hard requirements. These should be treated as stronger than preferences.

### preferences.md

Optional soft user or project preferences. These guide choices but can be overridden by explicit user requests. Do not place machine-specific paths in shared memory without confirmation.

### do-not-use.md

Rejected options, known failed paths, and tombstones. Agents should check it before reintroducing approaches. Keep tombstones newest first.

### inbox.md

Temporary holding area for memory candidates that need review or compaction. Keep new candidates newest first.

### changelog.md

Optional memory maintenance log. Keep it factual, brief, and newest first.

### rules/

Optional task-specific rules. List enabled rule files in the manifest optional module index, then load a rule file only when the current task clearly matches it.

### profiles/

Optional workflow-specific rules. Keep Git, release, ticket, docs, and research workflows out of the core protocol. List enabled profile files in the manifest optional module index, then load a profile only when its trigger matches.

### areas/

Optional area-specific memory for subsystems, monorepos, or large projects. Prefer an area over root decisions when a choice or invariant applies only to that subsystem. List enabled area files in the manifest optional module index, then load area files only when the task touches that area.

### archive/

Long-lived raw or old material. Do not load by default.
