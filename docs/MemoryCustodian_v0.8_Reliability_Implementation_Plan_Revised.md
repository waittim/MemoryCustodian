# MemoryCustodian v0.8 Reliability Implementation Plan — Revised

**Status:** Implemented
**Audience:** Development agent
**Target package version:** `0.8.0`
**Primary goal:** Improve semantic safety, routing determinism, write reliability, and bootstrap idempotency without expanding MemoryCustodian into a database, orchestration layer, or full lifecycle platform.

---

## 1. Scope summary

Implement exactly these seven workstreams:

1. Atomic writes for managed files.
2. Structure-safe, preview-first forgetting.
3. Privacy-correct `soft`, `hard`, and `purge` behavior.
4. Complete-entry context packing.
5. Manifest-authoritative runtime routing.
6. Idempotent managed blocks in Agent bootstrap files.
7. Basic CI and accurate contract-check terminology.

Do not add entry IDs, JSON APIs, YAML frontmatter, live Agent benchmarks, source freshness tracking, local/shared memory overlays, or any other explicitly excluded feature.

---

## 2. Execution contract

Before changing code:

1. Read `AGENTS.md`.
2. Read `docs/memory/manifest.md`.
3. Read `docs/memory/brief.md`.
4. Load only the memory files required for implementation and review.
5. Run and record the baseline checks.
6. Preserve stdlib-only and offline-first operation.
7. Keep changes small and reviewable.
8. Do not perform unrelated cleanup.

Baseline commands:

```bash
PYTHONPATH=cli python3 -m unittest discover -s tests
PYTHONPATH=cli python3 scripts/check-skill-evals.py
PYTHONPATH=cli python3 -m memory_custodian.main check
git diff --check
```

If an existing test fails before implementation, record it clearly and do not silently change unrelated behavior to make it pass.

---

## 3. Global design constraints

The following constraints apply to every workstream:

- Durable memory remains plain Markdown.
- The project remains usable without network access.
- Runtime dependencies remain Python standard library only.
- The manifest remains Markdown in v0.8.
- Human-editability remains a first-class property.
- Existing valid protocol `0.5` projects should continue to work unless a real protocol change is required.
- Commands must fail clearly rather than silently substitute hidden behavior.
- Safety-critical mutations should be previewable before application.
- Semantic units must not be mechanically truncated or partially deleted.
- Git remains optional; no feature may require Git.
- No background service, database, index, or lock manager is introduced.

---

## 4. Definition of success

The release is complete only when:

- `forget` is dry-run by default.
- Forgetting removes complete semantic units, never arbitrary matching lines.
- Short topics are protected against broad accidental deletion without banning legitimate terms such as `Go`, `UI`, `R`, or `C`.
- `hard` and `purge` do not persist or unnecessarily echo the forgotten topic.
- `read` never cuts a decision, tombstone, bullet, or H2 section in half.
- Runtime task routing comes from the project manifest.
- Missing, malformed, ambiguous, or unsafe manifest routes fail clearly.
- Agent bootstrap snippets are managed idempotently and cannot be duplicated by `--force-agent`.
- Managed file writes use atomic replacement.
- CI runs the current unit, contract, memory, and whitespace checks.
- Existing static checks are described as contract checks, not live Agent behavior evaluations.
- No explicit non-goal is implemented.

---

# Workstream A — Atomic managed-file writes

## Objective

Prevent interrupted or failed writes from leaving partially written managed files.

## Likely files

- `cli/memory_custodian/protocol.py`
- Mutation command modules
- New or existing write-helper tests

## Required implementation

Replace the shared direct write path with same-directory atomic replacement.

The shared writer should:

1. Create the destination parent directory if needed.
2. Normalize the trailing newline using existing behavior.
3. Create a uniquely named temporary file in the same directory.
4. Write UTF-8 text.
5. Flush the temporary file.
6. Attempt `os.fsync()` on the temporary file.
7. Replace the destination with `os.replace()`.
8. Remove the temporary file if an exception occurs before successful replacement.

All managed writes must flow through the shared helper, including:

- initialization
- add
- enable
- compact
- forget
- migrate
- manifest updates
- Agent bootstrap file updates

Reading test fixtures may continue to use `Path.write_text()` inside tests.

## Platform guidance

Do not turn filesystem durability into a portability blocker.

- `os.replace()` is required.
- File `fsync()` should be used where supported.
- Do not add directory `fsync()`, platform-specific durability layers, or a transaction log in this version.
- Errors must remain actionable and preserve the original destination where possible.

## Required tests

- Creating a new file produces correct content.
- Replacing an existing file produces correct content.
- A trailing newline is preserved.
- A simulated `os.replace()` failure leaves the original destination unchanged.
- A failed operation removes the temporary file.
- Existing mutation command tests continue to pass.
- No managed production code directly calls `Path.write_text()` outside the shared writer.

## Acceptance criteria

- There is one common atomic write implementation.
- No file locking, journal, rollback system, or multi-file transaction engine is introduced.

---

# Workstream B — Structure-safe, preview-first forgetting

## Objective

Make forgetting explicit, predictable, and structurally safe.

## Likely files

- `cli/memory_custodian/main.py`
- `cli/memory_custodian/forget.py`
- `cli/memory_custodian/protocol.py` or a small internal Markdown-unit helper
- `tests/test_add_forget_compact.py`
- README, CLI help, release notes

## CLI contract

Forgetting is dry-run by default:

```bash
memory-custodian forget "SQLite"
memory-custodian forget "SQLite" --apply
memory-custodian forget "Go"
memory-custodian forget "Go" --apply --allow-broad-match
memory-custodian forget "private topic" --mode hard --apply
memory-custodian forget "private topic" --mode purge --apply
```

Add:

```text
--apply
--allow-broad-match
```

The default command must not mutate files.

## Literal matching rules

- Match literally and case-insensitively.
- Do not interpret the topic as a regular expression.
- Normalize surrounding whitespace in the supplied topic.
- An empty topic is invalid.

## Semantic unit parsing

Parse managed Markdown into complete removable units.

### H2 unit

An H2 heading and all following content up to the next H2 heading form one unit.

Example:

```markdown
## 2026-07-18 - Use SQLite
Decision:
Use SQLite for local storage.
Reason:
It keeps the runtime offline.
```

A match anywhere in this unit removes the whole unit.

### Top-level bullet unit

A top-level bullet outside an H2 section forms one removable unit.

Continuation lines indented beneath that bullet belong to the same unit when present.

### Non-removable structure

Do not remove:

- the H1 document title
- explanatory preamble text
- structural headings
- `manifest.md`
- `README.md` files inside the memory directory
- platform bootstrap files during topic removal
- `do-not-use.md` while searching for old content to remove

Never delete only the matching line from a structured entry.

## Broad-match protection

Do not categorically reject short legitimate topics.

Treat a topic as broad-risk when either condition is true:

- it contains fewer than four non-whitespace characters; or
- the dry run matches more than one semantic unit.

Behavior:

- Dry-run preview is always allowed.
- `--apply` must refuse a broad-risk plan unless `--allow-broad-match` is provided.
- A clear error must explain why the match is considered broad.
- Even with `--allow-broad-match`, deletion still occurs only at complete-unit boundaries.

This protects against accidental deletion while permitting real terms such as `Go`, `UI`, `R`, `C`, and `DB`.

## Search scope by mode

### `soft`

Search:

- core active memory files
- enabled active optional files
- active `areas/`, `rules/`, and `profiles/`

Do not search `archive/`.

### `hard`

Search the same active memory scope as soft mode.

### `purge`

Search:

- all active memory
- enabled and existing optional files
- `archive/`

Do not search or modify repository documentation outside managed memory.

## Complete mutation plan before writing

Before the first file mutation:

1. Resolve the complete target file set.
2. Read every target file.
3. Parse every file into semantic units.
4. Calculate every removal in memory.
5. Calculate the planned tombstone and changelog behavior.
6. Validate all resulting file contents.
7. Validate broad-match requirements.
8. Print or retain one complete mutation plan.
9. Only then begin writing.

Write order:

1. Modified source memory files.
2. `do-not-use.md`, when required.
3. `changelog.md`, when enabled and required.

This is not a multi-file transaction. Do not implement rollback or journaling. If a later write fails, report exactly which files were successfully written and which step failed.

## Preview output

Dry-run output must include:

- selected mode
- searched file count
- matched file count
- total matched semantic units
- planned tombstone behavior
- planned changelog behavior
- whether broad-match confirmation is required
- instruction to rerun with `--apply`

For normal soft mode, previews may show matched headings or bullet summaries.

For hard and purge mode:

- avoid unnecessarily printing the forgotten topic;
- redact a heading when the heading itself contains the topic;
- prefer file path plus a neutral unit number or label.

Example:

```text
Mode: hard
Searched files: 8
Matched files: 2
Matched units: 3
- decisions.md: [redacted matching entry]
- areas/backend.md: entry 2
Tombstone: generic redacted guard
Changelog: generic hard-forget record
Dry run only. Re-run with --apply.
```

## Mode semantics

### Soft

- Remove matching complete units from active memory.
- Add a topic-bearing tombstone to `do-not-use.md`.
- A soft-mode changelog entry may include the topic.
- If there are no matches, `soft --apply` may still add the tombstone because the user explicitly asked to prevent future reintroduction.

### Hard

- Remove matching complete units from active memory.
- Add a generic redacted tombstone.
- Do not persist the original topic in the tombstone.
- Do not persist the original topic in the changelog.
- Do not echo the topic in final output beyond what the user typed in the invocation context.

Suggested tombstone wording:

```text
A user-requested topic was removed in hard mode. Do not reconstruct removed content from prior context unless the user explicitly reverses this request.
```

### Purge

- Remove matching complete units from active memory and archive.
- Do not write a topic-bearing tombstone.
- Prefer no tombstone; if a guard is considered necessary, it must remain generic and not encode the topic.
- Changelog records only that a purge operation occurred.
- Print a warning that Git history, backups, caches, and external copies are outside the command's scope.

## Required tests

- Default invocation is dry-run.
- Dry-run changes no files.
- `--apply` performs the exact previewed plan.
- H2 title matches remove the whole H2 unit.
- H2 body matches remove the whole H2 unit.
- Bullet matches remove the complete bullet unit.
- Surrounding Markdown remains valid.
- Empty topics are rejected.
- Short topics can be previewed.
- Short topics require `--allow-broad-match` when applying.
- Multi-unit matches require `--allow-broad-match`.
- A single unambiguous long-topic match does not require the flag.
- `soft` writes a topic-bearing tombstone.
- `soft --apply` with zero matches can still add a tombstone.
- `hard` does not preserve the topic in tombstone, changelog, or final output.
- `purge` removes archive matches and does not preserve the topic.
- `manifest.md` is never modified.
- Mutation planning completes before the first write.
- A simulated later-write failure reports partial completion accurately.
- Existing forgetting tests are updated to the new CLI contract.

## Acceptance criteria

- No line-by-line destructive deletion remains.
- Broad matches require explicit confirmation.
- Hard and purge modes are privacy-correct.
- No transaction engine is added.

---

# Workstream C — Complete-entry context packing

## Objective

Ensure token budgets never produce semantically incomplete memory.

## Likely files

- `cli/memory_custodian/protocol.py`
- `cli/memory_custodian/read.py`
- Shared semantic-unit parsing helper
- `tests/test_read_status.py`

## Required implementation

Replace raw string truncation with complete-entry packing.

For each loaded file:

1. Preserve the H1 title.
2. Preserve a short preamble before the first semantic unit.
3. Parse the body into:
   - H2 units when H2 entries exist;
   - otherwise top-level bullet units;
   - otherwise one complete body unit.
4. Add complete units in source order.
5. Stop before adding a unit that would exceed the file budget.
6. Never cut inside a unit.
7. Report how many units were omitted.

Example metadata:

```text
Omitted:
- decisions.md: 3 complete entries omitted because of the 800-token budget
```

## Oversized atomic unit

If the first semantic unit exceeds the file budget:

- include it whole;
- report that one atomic entry exceeds the budget;
- do not truncate it;
- continue to let `status` and `check` report the health issue.

Semantic integrity is more important than falsely satisfying the budget.

## Preamble handling

Do not allow an unusually long preamble to consume the entire budget silently.

- Preserve the title.
- Treat the remaining preamble as one complete unit.
- If that unit itself exceeds budget, include it whole with an oversized-unit warning.
- Do not add a second truncation mechanism for preambles.

## Preserve existing behavior

- `--names-only` still renders no file content.
- File ordering remains stable.
- Required and optional file handling remains stable except for manifest error behavior described in Workstream D.
- The existing offline token estimator may remain.
- Do not add relevance ranking or entry metadata.

## Required tests

- Decision content is never cut between `Decision:` and `Reason:`.
- Tombstones are never partially included.
- Bullets are never partially included.
- Multiple units are packed in original order.
- Omitted counts are correct.
- One oversized unit is included whole with a warning.
- A long preamble is treated atomically.
- `--names-only` output remains compatible.
- Missing required files still produce nonzero status.
- The old `[Trimmed to ...]` behavior is removed.

## Acceptance criteria

- Every rendered semantic entry is complete.
- No `priority`, `status`, `last_verified`, semantic score, embedding, tokenizer dependency, `--strict`, or `--best-effort` mode is introduced.

---

# Workstream D — Manifest-authoritative runtime routing

## Objective

Make the project manifest the only runtime source of task-to-file routing and eliminate silent fallback.

## Likely files

- `cli/memory_custodian/protocol.py`
- `cli/memory_custodian/main.py`
- `cli/memory_custodian/read.py`
- `cli/memory_custodian/check.py`
- `cli/memory_custodian/templates.py`
- `tests/test_read_status.py`

## Design decision

For an initialized project, `docs/memory/manifest.md` is authoritative for which files a task loads.

Python may define:

- supported CLI task names;
- task aliases;
- canonical route categories;
- parser and validation behavior.

Python must not define a second hidden category-to-file route used as a normal runtime fallback.

## Canonical route categories

Use an explicit task-to-category mapping, for example:

```text
default, general -> general
planning, architecture, refactoring -> planning
implementation, execution, debugging -> implementation
artifact, output -> artifact
preferences -> preferences
recap, history, status -> history
maintenance, compact, forget -> maintenance
```

This mapping does not contain file paths.

The manifest defines the file paths for each category.

## Heading resolution

Continue using Markdown headings, but make matching deterministic.

Requirements:

- Normalize case and surrounding whitespace.
- Match only documented canonical route headings or documented exact aliases.
- Do not use unrestricted substring matching.
- If zero sections match a required category, fail.
- If more than one section matches a category, fail as ambiguous.
- Error messages must identify the category and candidate headings.

Examples that must not silently match:

```markdown
### Implementation notes
### Old implementation route
### Coding work
```

unless the parser explicitly documents those headings as valid aliases.

## Manifest path validation

Every parsed memory path must:

- be relative;
- stay under the configured memory directory;
- use a `.md` path when it refers to a file;
- reject `..`;
- reject absolute paths;
- reject empty paths;
- reject malformed bullet text that is not a path.

Deduplicate repeated paths deterministically while preserving first appearance and requiredness.

## Missing or malformed manifest behavior

When the memory directory exists but `manifest.md` is missing:

- fail clearly;
- recommend restoring the manifest, applying an applicable migration, or carefully reinitializing;
- do not silently use Python routes.

When the requested route is malformed or missing:

- fail clearly;
- identify the category;
- do not return a partial default pack.

## `check` requirements

`memory-custodian check` should validate before `read` encounters the problem:

- protocol metadata
- always-load section
- all supported canonical route categories
- exact or documented heading matches
- ambiguous headings
- valid safe paths
- missing required routes
- optional index consistency
- duplicate route paths
- unsafe paths

## Protocol version decision

Keep protocol `0.5` only if:

- existing valid `0.5` manifests require no edits;
- only parser strictness, fallback removal, and validation behavior change;
- canonical headings already used by valid manifests remain accepted.

Bump to protocol `0.6` if implementation requires any of the following:

- changing required heading text;
- adding mandatory route syntax;
- changing manifest semantics;
- requiring fields that existing valid `0.5` manifests do not contain.

If a bump is required:

- add a deterministic migration;
- preserve customized content;
- document the exact compatibility impact;
- add migration fixtures.

Do not avoid a justified protocol bump by adding hidden heuristics.

## Required tests

- Default initialized manifests resolve every supported task.
- Customized valid routes are honored.
- Missing manifest fails clearly.
- Missing category fails clearly.
- Ambiguous headings fail clearly.
- Unsafe absolute and traversal paths fail.
- Duplicate paths are deduplicated deterministically.
- No silent Python route fallback occurs.
- Existing valid `0.5` manifests continue to work if the protocol remains `0.5`.
- Migration tests cover any required `0.6` change.
- `check` reports routing issues proactively.

## Acceptance criteria

- Runtime routing has one project-level source of truth.
- Markdown remains the manifest format.
- No YAML, JSON companion file, or schema dependency is introduced.

---

# Workstream E — Managed Agent bootstrap blocks

## Objective

Make bootstrap installation idempotent and prevent duplicate MemoryCustodian sections in `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md`.

## Likely files

- `cli/memory_custodian/init.py`
- `cli/memory_custodian/main.py`
- `tests/test_init.py`
- Adapter documentation and release notes

## Managed block format

Newly generated snippets should use:

```markdown
<!-- memory-custodian:start -->
## MemoryCustodian

This project uses MemoryCustodian for local project memory.

...

<!-- memory-custodian:end -->
```

Markers must be exact and stable.

## Required behavior

### No existing block

Append exactly one managed block.

### Existing complete managed block

- Default initialization keeps it unchanged.
- `--force-agent` replaces the block in place.
- `--force-agent` must never append a second block.

### Incomplete markers

If only one marker exists:

- fail for that Agent file;
- do not append;
- explain that the managed block is malformed and needs review.

### Multiple managed blocks

- fail clearly;
- do not choose one arbitrarily;
- do not append another block.

### Legacy unmarked section

A legacy file may contain:

```markdown
## MemoryCustodian
```

without managed markers.

Behavior:

- default: keep the legacy section and report that it is unmanaged;
- do not append a second MemoryCustodian section;
- `--force-agent`: convert the detected legacy section to one managed block only when the section boundary can be identified safely;
- if safe conversion is uncertain, fail and require manual review.

Do not implement a general Markdown section editor. Support only the repository's known legacy snippet shape.

## Scope limits

Do not add in v0.8:

- `uninstall`
- `sync-agent-files`
- bootstrap version metadata
- rollback support
- a separate bootstrap migration command

## Required tests

- Fresh initialization adds one managed block.
- Repeated initialization does not duplicate it.
- `--force-agent` replaces in place.
- Incomplete markers cause a clear failure.
- Multiple blocks cause a clear failure.
- Legacy known-format sections are detected.
- Default behavior does not duplicate a legacy section.
- Safe forced conversion creates one managed block.
- Uncertain legacy structure does not get rewritten.
- Existing unrelated file content remains unchanged.

## Acceptance criteria

- Agent bootstrap files are idempotent.
- No duplicate section can be created through supported initialization paths.

---

# Workstream F — Basic continuous integration

## Objective

Automatically run the checks contributors are already expected to run.

## File

- `.github/workflows/ci.yml`

## Required workflow

Trigger on:

- pull requests
- pushes to the default branch

Use:

- `ubuntu-latest`
- Python `3.10`
- Python `3.13`

Required steps:

```bash
python -m pip install -e .
PYTHONPATH=cli python -m unittest discover -s tests
PYTHONPATH=cli python scripts/check-skill-evals.py
PYTHONPATH=cli python -m memory_custodian.main check
git diff --check
```

The workflow should remain small and understandable.

## Required validation

- Passes on a clean checkout.
- Fails on unit-test failure.
- Fails on contract-check failure.
- Fails on repository memory-check failure.
- Fails on whitespace errors.

## Acceptance criteria

Do not add:

- coverage gates
- nightly runs
- multi-OS matrices
- release automation
- external test services
- Python versions beyond the two selected versions in this release

---

# Workstream G — Accurate contract-check terminology

## Objective

Accurately describe existing static checks without claiming live model behavior evaluation.

## Likely files

- `scripts/check-skill-evals.py`
- `README.md`
- `CONTRIBUTING.md`
- tests
- `RELEASE-NOTES.md`

## Required terminology

Prefer:

- skill contract checks
- static scenario validation
- contract scenarios
- behavioral specification scenarios

Avoid describing the current script as proving actual Agent compliance.

Update output from:

```text
MemoryCustodian skill eval check
```

to:

```text
MemoryCustodian skill contract check
```

Document that the checker validates:

- required Skill instructions
- scenario file structure
- required observations
- forbidden outcomes
- presence of contractual wording

Also document that it does not execute:

- Codex
- Claude Code
- Gemini
- another model runtime

## Compatibility

Keep the existing script filename and `evals/` directory in v0.8 to avoid unrelated rename churn.

## Required tests

- Existing contract failures remain detectable.
- Output uses the new terminology.
- README and CONTRIBUTING commands remain valid.
- No live Agent harness is introduced.

---

# 5. Shared implementation guidance

## Reuse semantic-unit parsing carefully

Forgetting and context packing both need H2 and bullet units.

A small shared helper is encouraged if it:

- remains internal;
- has a narrow API;
- preserves source order;
- returns source spans or reconstructed content reliably;
- avoids becoming a general Markdown parser.

Do not introduce a third-party Markdown parser.

Suggested internal concepts:

```text
MarkdownDocument
MarkdownUnit
unit.kind = preamble | h2 | bullet | body
unit.text
unit.start_line
unit.end_line
unit.heading
```

These need not become public classes if simple functions are clearer.

## Error behavior

Use existing CLI error conventions where possible, but improve clarity.

Do not introduce a full stable exit-code taxonomy in v0.8.

At minimum:

- successful operation or healthy check: `0`
- failed validation, unsafe mutation, missing route, or health failure: nonzero
- argparse remains responsible for argument syntax errors

## Documentation synchronization

Update:

- README
- CONTRIBUTING
- CLI help text
- release notes
- relevant Skill references
- repository dogfood memory only for durable decisions

Do not copy the entire plan into project memory.

---

# 6. Recommended implementation order

## Phase 1 — Shared safety foundation

1. Implement atomic writes.
2. Add atomic-write tests.
3. Implement narrow semantic-unit parsing helpers.
4. Verify no existing behavior regresses.

## Phase 2 — Forget safety

1. Build complete in-memory mutation planning.
2. Add default dry-run and `--apply`.
3. Add broad-match detection and `--allow-broad-match`.
4. Implement complete-unit deletion.
5. Implement soft, hard, and purge privacy semantics.
6. Add preview redaction.
7. Complete forgetting tests.

## Phase 3 — Context integrity

1. Replace raw truncation with complete-unit packing.
2. Add omitted-unit reporting.
3. Handle oversized atomic units.
4. Complete read tests.

## Phase 4 — Routing determinism

1. Separate task aliases from route file definitions.
2. Remove runtime `TASK_FILE_MAP` fallback.
3. Implement exact category resolution.
4. Detect missing and ambiguous sections.
5. Validate route paths.
6. Strengthen `check`.
7. Decide whether protocol remains `0.5` or becomes `0.6`.
8. Add migration only if justified.

## Phase 5 — Bootstrap idempotency

1. Add managed markers.
2. Replace complete blocks in place.
3. Detect malformed and duplicate blocks.
4. Handle known legacy snippets conservatively.
5. Complete initialization tests.

## Phase 6 — Assurance and documentation

1. Add CI.
2. Correct contract-check terminology.
3. Update documentation and release notes.
4. Update package version.
5. Run final validation.
6. Build and inspect the plugin archive.

---

# 7. Suggested commit structure

Prefer independently reviewable commits:

1. `Use atomic writes for managed files`
2. `Add semantic Markdown unit parsing`
3. `Make forget preview-first and structure-safe`
4. `Preserve complete entries in context packs`
5. `Make manifest routing authoritative`
6. `Manage Agent bootstrap blocks idempotently`
7. `Add CI and clarify contract-check terminology`
8. `Prepare v0.8.0 release documentation`

Do not mix unrelated formatting or refactoring into these commits.

---

# 8. Required final validation

Run from a clean working tree:

```bash
python3 -m pip install -e .
PYTHONPATH=cli python3 -m unittest discover -s tests
PYTHONPATH=cli python3 scripts/check-skill-evals.py
PYTHONPATH=cli python3 -m memory_custodian.main check
python3 scripts/package-codex-plugin.py --allow-dirty --output /tmp/memory-custodian-v0.8-test.zip
git diff --check
```

Manually validate in temporary projects:

```bash
# Initialize twice; no duplicate bootstrap block.
memory-custodian init --project-root /tmp/mc-test --agent all
memory-custodian init --project-root /tmp/mc-test --agent all

# Force replacement; still only one managed block.
memory-custodian init --project-root /tmp/mc-test --agent all --force-agent

# Preview forget; no mutation.
memory-custodian forget "SQLite" --project-root /tmp/mc-test

# Apply one unambiguous match.
memory-custodian forget "SQLite" --apply --project-root /tmp/mc-test

# Preview a short topic.
memory-custodian forget "Go" --project-root /tmp/mc-test

# Broad apply must require explicit confirmation.
memory-custodian forget "Go" --apply --project-root /tmp/mc-test
memory-custodian forget "Go" --apply --allow-broad-match --project-root /tmp/mc-test

# Hard mode must not persist the topic.
memory-custodian forget "sensitive topic" --mode hard --apply --project-root /tmp/mc-test

# Purge must include archive but not Git history.
memory-custodian forget "retired topic" --mode purge --apply --project-root /tmp/mc-test

# Read must preserve complete entries.
memory-custodian read --task implementation --project-root /tmp/mc-test

# A customized valid manifest must be authoritative.
memory-custodian read --task implementation --project-root /tmp/mc-custom

# A malformed or ambiguous manifest must fail clearly.
memory-custodian check --project-root /tmp/mc-invalid
memory-custodian read --task planning --project-root /tmp/mc-invalid
```

Inspect the resulting Markdown files directly.

---

# 9. Explicit non-goals

Do not implement any of the following in this plan:

- stable IDs for memory entries
- entry status or lifecycle state
- `show`, `edit`, `supersede`, `review`, or lifecycle CRUD commands
- supersession graphs
- entry author or owner metadata
- source file metadata
- Git blob SHA tracking
- freshness or reachability audit commands
- databases
- indexes
- embeddings
- RAG
- vector search
- background services
- file locking
- distributed concurrency control
- transaction journals
- multi-file rollback
- shared/local memory overlay systems
- `.memory-local/`
- JSON or YAML manifest replacement
- YAML frontmatter
- stable JSON CLI contract
- stable multi-code exit taxonomy
- sensitive-information scanner
- secret scanner
- live cross-Agent evaluation harness
- automated benchmark platform
- relevance scoring
- semantic ranking
- exact third-party tokenizers
- `read --strict`
- `read --best-effort`
- bootstrap uninstall
- bootstrap synchronization command
- one-entry-per-file decision mode
- directory-mode migration
- Homebrew, npm, Docker, or standalone binary distribution
- PyPI release work unless separately requested
- official marketplace submission
- README benchmark claims without measured evidence
- broad codebase cleanup unrelated to the seven workstreams

When an implementation choice appears to require one of these, choose a smaller design or stop and document the blocker.

---

# 10. Definition of done

The work is done when:

1. All unit tests pass locally.
2. All static skill contract checks pass.
3. Repository memory checks pass.
4. CI passes on Python 3.10 and 3.13.
5. Forgetting is dry-run by default.
6. Broad matches require explicit confirmation.
7. Hard and purge modes do not preserve the original topic.
8. Forgetting removes only complete semantic units.
9. Mutation planning completes before the first write.
10. Context packs contain only complete semantic units.
11. Missing or malformed manifest routing never silently falls back.
12. Valid customized manifests remain authoritative.
13. Agent bootstrap files cannot receive duplicate managed blocks.
14. Managed writes use atomic replacement.
15. Documentation accurately describes new behavior and compatibility.
16. Release notes state whether protocol remains `0.5` or moves to `0.6`, and why.
17. The package and plugin metadata are ready for `v0.8.0`.
18. No explicit non-goal was implemented.
