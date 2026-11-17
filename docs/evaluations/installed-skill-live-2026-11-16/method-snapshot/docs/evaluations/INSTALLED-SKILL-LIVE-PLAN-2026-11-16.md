# Fixed installed-Skill live smoke plan — 2026-11-16

This fixes three development smoke tasks before any live result collection.
It tests explicitly invoked, project-local installed MemoryCustodian Skill/CLI
use in Codex. It does not test automatic Skill discovery, marketplace installation,
general effectiveness, checkpoint benefit, or other agent runtimes.

## Fixed tasks

Each task uses one independent, ephemeral Codex session and its own fresh
temporary checkout. Do not replace failures, change tasks after inspecting live
outcomes, retry based on scores, or reuse another task's history.

1. `scoped-implementation`: implement `src/account.py`'s `account_label` using
   the project's label rule, while retaining its input validation. The exact
   label rule is supplied only in active, evidence-backed project memory. A
   successful, complete strict implementation read with the explicit source
   path must occur in a separate tool event before any observed code write.
   Hidden mechanical checks cover zero, ordinary and larger integers, and
   invalid inputs. The visible task permits edits only to `src/account.py`;
   active memory and the installed distribution stay unchanged. Other memory
   updates may be proposed in the final reply instead of written.
2. `missing-scope`: perform implementation admission using exactly the caller's
   empty path/area scope. The fixture enables a path-routed area. The installed
   strict read must report `INCOMPLETE`, and no source or memory file may change.
   The visible task requests a final-reply report without file edits; it does
   not supply the expected admission result.
3. `unconfirmed-observation`: record an expressly unconfirmed agent observation
   using the installed memory workflow. A complete strict maintenance read
   precedes the memory write. The result must be exactly one candidate with
   unconfirmed evidence in `inbox.md`, with the observation retained and no
   active memory or source-code changes. The visible task explicitly limits
   writes to the inbox and exactly one candidate for this observation. No user
   confirmation is inferred.

## Installation and preparation

Copy the actual `cli`, `skills`, `bin`, and bundled script files into the
fixture's `.installed/memory-custodian` distribution. Link the genuine Skill
under `.agents/skills/memory-custodian`, pointing inside that distribution.
The task and `AGENTS.md` explicitly identify the installed Skill file and CLI
entry point. This is manual invocation; it does not establish native discovery.

Use the real installed CLI to initialize memory, curate the brief, create a
Subject using preview and matching Plan ID, add a declared synthetic confirmed
constraint, and enable a source-path area. Do not fabricate protocol entries.
The initial label rule is fixture-author-provided `user-confirmed` evidence;
live agents do not supply that confirmation. No answers or grader code are
copied into the runtime checkout. Preparation records actual version and source
hashes; no package version is assumed.

Do not change `HOME`, `CODEX_HOME`, global installation, configuration, or
authentication. Use existing CLI authentication without copying credentials.
Each fixture has a separate temporary `XDG_STATE_HOME` outside the checkout;
the sandbox may add only that temporary state directory as writable. Its
contents must not be loaded into agent context. Remove temporary material at
the end and retain only normalized evidence.

## Runtime and observations

- Real Codex CLI `exec --json`, requested model `gpt-6.1-sol`, reasoning `low`.
- Each task has a 180-second runtime budget; run tasks sequentially.
- `workspace-write`, agent shell network disabled, approval `never`.
- Ignore user configuration; disable host Skill discovery, bundled Skills,
  apps, plugins, web search, external memories, delegation, and shell snapshots.
  Do not disable project Skills or the ability to read the installed files.
- Source evidence includes the exact adapter/script/plan/helper hashes, complete
  installed-distribution hashes, fixture hash before execution, task/prompt
  hashes, CLI version/binary hash, unique session identity and one successful
  turn-completion event.
- Raw command arguments, stdout/stderr, prompts, reasoning, public-message text,
  credentials and machine paths are not retained. Public messages and command/
  output payloads receive hashes only. Normalized tool metadata may describe
  routing and mutation events without copying their payloads.

A command merely mentioning `read` is insufficient. In memory, inspect the
actual tool result for the versioned installed CLI JSON envelope and retain only
allowlisted schema/status/routing/task fields and event order. Skill-file
inspection needs both a relevant command path and matching Skill content.
The visible invocation instructions require the complete, unfiltered CLI JSON
envelope in tool output, rather than a pipe that extracts only rendered text.
Write ordering uses observed `file_change` events and conservative shell-write
classification. If a changed artifact has no observable write boundary, mark
that ordering proof insufficient, rather than inventing a successful proof.
These observations are not tamper-proof runtime attestation against a malicious
agent forging CLI output. Missing observations do not become zero or PASS.

## Acceptance and interpretation

PASS requires real-runtime completion, installed Skill inspection, the relevant
strict-read evidence, all task-specific artifact checks, unchanged installed
sources, and no forbidden external tools. Runtime/authentication unavailability,
timeout, malformed or incomplete JSONL, or changed grading/support sources are
`BLOCKER`. A completed agent that violates the task contract is `FAIL`; evidence
that cannot establish a required ordering is `REVIEW`. Offline runtime stubs
retain an explicitly offline evidence class and must never become live results.

Retain all three task records append-only, including failure and infrastructure
outcomes. Record hashes and a summary without overwriting existing files. Any
follow-up uses a separately fixed plan and new record directory. Three small,
previously described development tasks cannot establish comparative benefits,
reliability across repositories, cost savings, or full multi-agent conformance.

## Reproduction

```bash
python3.13 scripts/run-installed-skill-eval.py \
  --codex-executable codex --model-version gpt-6.1-sol \
  --record-dir docs/evaluations/installed-skill-live-2026-11-16 \
  --report-file docs/evaluations/INSTALLED-SKILL-LIVE-RESULTS-2026-11-16.md
```

Run only after reviewing this plan and freezing method sources. The preparation
and unit tests do not launch a model. Do not label their results live evidence.
