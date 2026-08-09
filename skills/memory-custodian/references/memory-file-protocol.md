# Memory File Protocol

## Protocol 0.7 admission

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

Area decisions use `MC-AREA` with a `Decision` body. Area constraints, preferences, and rejected approaches retain
their semantic `MC-CON`, `MC-PREF`, and `MC-DNU` IDs and typed bodies while using `Scope: area:<slug>` and
`areas/<slug>.md`. Validation is bidirectional: Entry ID, typed body, storage path, and Scope must agree.

Protocol 0.7 manifests include entry and Subject schema version 1 plus routing and conflict schema version 1, a
persistent UUIDv4 `project_id`, `subject_registry: subjects.md`, `admission_policy: evidence-required`,
`routing_policy: explicit-task-and-scope`, and `conflict_policy: canonical-subject-and-review`. The project ID is
identity for external locks and local-overlay namespaces, not authentication or authorization.

## Concurrency and plan confirmation

Mutation locks live in private platform state outside the repository. Every writer first acquires a bootstrap lock
derived from the normalized project path, re-reads the manifest, and then—while still holding the bootstrap
lock—acquires the permanent project lock when a valid `project_id` exists or is being installed. Protocol 0.5
compatibility writes keep their legacy format and confirmation behavior but remain serialized under the bootstrap
guard. Every mutation is rebuilt while the applicable guard is held.

Preview-first commands hash a repo-relative private execution plan containing base and expected output digests.
Public previews are a separate representation. Hard and purge previews omit raw topic arguments and file digests,
and redact matching topic text from public path and blocker metadata; their private confirmation plan is salted
with a repo-external random nonce. Protocol 0.7 apply requires the matching Plan ID and refuses every write if any
target changed.

Private state directories use mode `0700` and state files use `0600` on POSIX. State reads and writes reject
symlinks, non-regular files, and files owned by another user. Well-formed stale locks require the same-host,
dead-PID, and 60-second checks. Malformed lock residue is recoverable only with explicit stale-lock recovery after
five minutes. Preview seeds older than seven days are removed opportunistically on the next private-plan-state
access, after which callers must generate a new preview and Plan ID.

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

Protocol 0.7 permits every canonical Facet above for each managed entry type. The CLI still validates through an
explicit type-to-Facet matrix; v0.11 intentionally defines no narrower type-specific exclusions. Narrowing or
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

Level 1 shared safety baseline:

- `brief.md`
- `constraints.md`

Level 2 task-specific:

- `decisions.md`
- `do-not-use.md`
- `preferences.md`, if declared by the task route
- `rules/*.md`, through a declared canonical task or explicit rule
- `profiles/*.md`, only through explicit profile input
- `areas/*.md`, through a declared path matcher or explicit area

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

Defines deterministic loading for explicit task and scope inputs. Optional declarations use the normative nested
grammar in `manifest-policy.md`; descriptions never act as machine routes.

### brief.md

The project-shape baseline. Keep it short, current, and focused on purpose, system shape, and active direction. A generated TODO or protocol description is not a valid project brief.

### decisions.md

Cross-cutting confirmed decisions with date, decision, and reason. Keep each entry within 120 tokens: one or two sentences for the choice and one sentence for the reason. Move supporting implementation detail elsewhere. Do not store brainstorming or subsystem-only choices here. Update or supersede older entries when the decision changes.

### constraints.md

Project-wide hard requirements and the generated substantial-work safety baseline. Move subsystem-only constraints
to a deterministically routed area to keep this file within budget.

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

Optional task-specific rules. Load only through declared canonical tasks or explicit `--rule` input.

### profiles/

Optional workflow-specific rules. Profiles are explicit-only; an adapter must expose the `--profile` choice.

### areas/

Optional subsystem memory. Load only through declared path globs or explicit `--area`; never infer from prose.

## Conflict and Reconciliation Records

Current active ownership is normalized `Scope + Subject ID + Facet`. Exact duplicate owners are conflicts.
Project/area overlap requires a valid area-to-project `Exception-To` relationship; multiple matched areas with the
same Subject/Facet require review. Exact Canonical-Ref or normalized alias collisions are deterministic conflicts,
while differently named Subjects are never auto-merged.

`reconciliations.md` may contain active `MC-REC` records with at least two canonical Entry IDs, admissible Evidence,
and `Resolution: distinct|superseded|exception|subject-merged`. Protocol 0.7 validates hand-maintained records and
previews Subject merges, but transactional governance apply waits for Protocol 0.8. Relationship resolutions name
exactly two Entries. A supersession requires a structurally valid active replacement retaining Scope, Subject, and
Facet. A Subject merge may retain a superseded historical source reference to the merged Subject, but its active
target must be structurally valid and match the source Scope and Facet. Promoted provisional identity is deferred
beyond Protocol 0.7.

Strict Protocol 0.7 reads, routing checks, governance previews, and ordinary mutation guards reject duplicate,
malformed, or wrong-level Protocol headings and malformed metadata. Legacy fallback requires no Protocol heading
trace at all. A present section requires a valid protocol version; a Protocol 0.7 section requires the complete
schema, Subject registry, UUIDv4 project identity, and policy metadata contract. Migrate and init repair may consume
incomplete inputs only when their complete candidate manifest passes strict validation before any write; ambiguous
sections require manual repair. One valid H2 plus any extra malformed Protocol heading trace is also ambiguous and
invalid. The current contract requires the canonical version spelling `0.7`; `0.7.0`, leading-zero equivalents, and
unsupported future versions are invalid rather than being routed with legacy grammar.
Public Subject, supersede, forget, compact, promotion, replacement, local-overlay, status, and focused-check commands
consume this same contract before operand lookup or Plan construction. Recovery syntax validation precedes pending
identity creation, so malformed input cannot leave a project or Entry seed behind.
Current-project preflight also validates all canonical routes. Fenced Markdown examples do not count as headings;
standalone HTML comments and valid closed fences are ignored, while code spans cannot open comment state and invalid
or unclosed fence/comment constructs fail closed. Setext, attached-hash, and four-space indented Protocol lookalikes
are malformed traces, not metadata sections. Canonical task H3 routes must be direct content of exactly one
`Load by task` H2. The Optional module index is unique; canonical subsections cannot repeat, declarations cannot
precede them, sentinels cannot coexist with declarations, and routing schema 1 accepts only `activation`, `tasks`,
`paths`, and `description`. Local overlay selection requires the resulting validated project identity.
Promotion and Subject merge reuse structural operand checks, and their Plan IDs bind the exact candidate, registry,
and referenced Entry state used by the preview. Local overlay selection validates the project-id state ancestor.
Local reset records directories/traversal failures, refuses symlink nodes without reading targets, and hashes regular
files through no-follow descriptors. Migration accepts operands only from normalized declarations contained in the
managed memory directory, reads every operand before creating pending identity state, and renders missing routes from
the same authority used by initialization.

## Local Overlay

Repo-external local modules use `Scope: local-user` or `Scope: local-machine`, require explicit normalized-root
binding, and load below all shared hard memory. They cannot redefine shared routes, hold secrets, or grant authority.

### archive/

Long-lived raw or old material. Do not load by default.
