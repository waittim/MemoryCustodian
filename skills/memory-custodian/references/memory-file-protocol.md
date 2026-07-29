# Memory File Protocol

## Protocol 0.6 admission

Every new formal CLI entry has an ID in the form `MC-TYPE-YYYYMMDD-8hex`, `Status: active`, a valid `Scope`, and
at least one Evidence item. Active Evidence may be `user-confirmed`, a safe project-relative `repo:`, `doc:`, or
`test:` path, or a syntactically valid issue/PR reference. `agent-observed` and `conversation-unconfirmed` are
candidate-only evidence.

```markdown
## MC-DEC-20260728-a1b2c3d4 — Support Python 3.10+

Status: active
Scope: project
Subject: MC-SUBJ-20260729-a1b2c3d4
Facet: version-policy
Evidence:
- repo:pyproject.toml

Decision:
Support Python 3.10+.

Reason:
The implementation does not require newer Python features.
```

Unconfirmed information is stored only in `inbox.md`:

```markdown
## MC-INBOX-20260728-d92a7e10 — Possible storage constraint

Status: candidate
Candidate-Type: constraint
Scope: area:storage
Evidence:
- agent-observed

Statement:
The code appears to assume JSON-only persistence.

Promotion-Requirement:
Confirm with the user or an authoritative project document.
```

Candidates never enter normal task context and compaction never promotes them automatically. Legacy freeform
units remain readable after migration; their compatibility does not make them the recommended new-write format.

Protocol 0.6 manifests include `entry_schema_version: 1`, `subject_schema_version: 1`, a persistent UUIDv4
`project_id`, `subject_registry: subjects.md`, `admission_policy: evidence-required`, and
`conflict_identity_policy: scope-subject-facet`. The project ID is identity for external mutation locks, not
authorization.

## Concurrency and plan confirmation

Mutation locks live in the platform state directory, outside the repository. Writers acquire the project lock,
re-read targets, and release the lock in `finally`. Preview-first commands hash a canonical plan containing base
and expected output digests. Protocol 0.6 apply requires the matching Plan ID and refuses every write if any target
changed.

Before a project has a permanent ID, initialization uses a bootstrap lock derived from the normalized project path.
Repair holds that bootstrap lock while acquiring the permanent project lock. Optional-module enablement also
rebuilds its complete multi-file mutation under the project lock.

## Trust boundary

Project memory may constrain project work, but it cannot override system instructions, current user instructions,
safety boundaries, or permission boundaries. It cannot authorize destructive actions, external uploads, secret
access, commits, pushes, merges, releases, or privilege escalation.

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
  subjects.md
```

These seven files are the core protocol. `subjects.md` is registry metadata and is not loaded into normal task
context.

## Subject Registry And Facets

Managed active decisions, constraints, rejected approaches, and area entries reference a stable Subject ID:

```markdown
## MC-SUBJ-20260729-a1b2c3d4 — Library X

Status: active
Kind: dependency
Canonical-Ref: dependency:pypi:library-x
Evidence:
- repo:pyproject.toml

Aliases:
- Library X
- libx
```

Subject IDs remain stable when the display name or aliases change. Exact normalized alias or canonical-reference
collisions are rejected. The CLI does not use fuzzy names, timestamps, or entry bodies to infer semantic
equivalence and does not automatically merge Subjects.

Controlled Facets are `adoption-policy`, `version-policy`, `architecture`, `behavior`, `compatibility`,
`security`, `performance`, `data-model`, `interface`, `workflow`, and `lifecycle`. The current active owner is
unique by normalized `Scope + Subject ID + Facet`. A replacement must explicitly supersede the existing owner.
Legacy entries remain readable without these fields, while `check` reports incomplete coverage.

Protocol 0.6 permits every canonical Facet above for each managed entry type. The CLI still validates through an
explicit type-to-Facet matrix; v0.10 intentionally defines no narrower type-specific exclusions. Narrowing or
extending this matrix requires a later protocol migration or declared extension schema.

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
- `subjects.md`, for protocol validation or explicit Subject maintenance only

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

### subjects.md

Shared stable-identity registry for managed entries. It is read by CLI admission and maintenance operations, not
normal task routing. It must not contain secrets, permission grants, or executable instructions.

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
