# Controlled benchmark harness

This directory is the v0.13 measurement foundation. It does not change Protocol 0.8, Entry schema 3, or the production CLI. A passing integrity check is not evidence that MemoryCustodian improves agent task success, reliability, or token use.

## What a run can answer

The harness prepares the same pinned task under four isolated conditions:

| Condition | What the checkout contains |
|---|---|
| `NO_MEMORY` | Repository code and visible tests. No `docs/memory/`, no `docs/manual/`, and no `AGENTS.md`. |
| `PLATFORM_FILE_ONLY` | A short bootstrap file only. This is an adoption baseline, not an information-matched control. |
| `EQUIVALENT_MANUAL_DOCS` | The same project facts as MemoryCustodian, written as ordinary documents under `docs/manual/`, plus a short map. |
| `MEMORYCUSTODIAN` | Those facts under `docs/memory/`, plus a bootstrap that points at the manifest. `docs/manual/` is removed. |

The primary comparison is `EQUIVALENT_MANUAL_DOCS` versus `MEMORYCUSTODIAN`. The other two conditions answer different questions and are not the incremental-value comparison.

Task files are JSON, not YAML. The runner stays on the Python standard library. The pinned fields are the roadmap task fields: repository, commit, prompt, touched paths, constraints, forbidden actions, test command, success oracle, memory dependencies, baseline notes, information parity, and condition visibility.

`repo.commit` is the SHA-256 of the fixture tree. These are purpose-built fixture repositories vendored in this repo so the grader can run without network access. They are not third-party production repositories. A public comparative claim still needs the held-out expansion below.

## Commands

Check schemas, fixture hashes, condition isolation, information parity, reference solutions, starter failures, and negative solutions:

```bash
python3 scripts/run-memory-bench.py --check-integrity
```

Plan one condition without writing a result and without launching an agent:

```bash
python3 scripts/run-memory-bench.py \
  --suite core \
  --runtime codex \
  --condition MEMORYCUSTODIAN \
  --dry-run
```

Grade the offline reference solution for one task:

```bash
python3 scripts/run-memory-bench.py \
  --mode offline-fixture \
  --runtime offline-fixture \
  --condition MEMORYCUSTODIAN \
  --task field-ledger-export-cap \
  --grade reference
```

`--mode live --runtime codex --codex-executable codex --model-version <model>`
explicitly enables the real Codex adapter. It uses a fresh sandboxed session
per task and records successful JSONL turn completion before grading. Without
that opt-in, live mode returns `BLOCKER` and evidence class
`live-runtime-unavailable`. A local `--mode command --agent-cmd ...` run is
evidence class `command-adapter`; a runtime label alone does not make it a
named-runtime result. See the [operator guide](../docs/evaluations/benchmark/RUNNING-BENCHMARKS.md).

Result files are append-only. The writer uses exclusive create and refuses to overwrite an existing result ID. Pass `--record-dir` only when a normalized record should be kept. Do not commit raw traces. Do not point an agent at the MemoryCustodian checkout; the harness builds a temp checkout that excludes other tasks, hidden oracles, and reference solutions.

## Pilot

Eighteen development-set tasks, nine in `field-ledger` and nine in `route-notes`:

- 6 constraint-sensitive implementation
- 3 architecture / planning
- 3 bug fixing
- 2 refactoring
- 2 history / prior-decision
- 2 stale or conflicting memory

At least half of the tasks depend on a fact that is not stated in the implementation file. Hidden oracles live under `benchmarks/oracles/` and are not copied into the checkout. `MEMORY_CONTEXT_OVERLOAD` is part of the label vocabulary and is not emitted, because the harness does not measure memory-context tokens or classify overload. Native Codex records observed total token usage, tool counts, and execution time separately from oracle outcomes.

## Claims

No comparative or latency claim is authorized by this pilot.

Before any claim-bearing run, set the smallest meaningful effect. The prespecified primary outcome is paired `task_success` for `EQUIVALENT_MANUAL_DOCS` versus `MEMORYCUSTODIAN`, with the task as the analysis unit. This development split cannot be used for that claim.

Held-out expansion, not yet authored:

- 3 pinned repositories
- 36 paired tasks
- separate from this development split
- public task-level comparisons need at least 30 paired tasks
- a general coding-effectiveness claim needs at least 3 repositories
- a named cross-agent claim needs a live result for every named runtime

Publish inconclusive results when the interval is wide. `PASS` means the requested harness operation or hidden oracle succeeded. It does not mean an agent beat a baseline.

## Package 0.13.0 boundary

The schema, fixtures, mechanical grader, isolation/parity checks, native Codex
adapter, batch runner, and [completed controlled pilot](../docs/evaluations/benchmark/RESULTS.md)
ship in package 0.13.0. All 18 tasks were run in four conditions, with 72
independent real sessions and no runtime blockers. The primary comparison did
not demonstrate incremental benefit over equivalent manual documents.

The pilot exercises each fixture's manifest/bootstrap path with host skills
disabled uniformly; it is not validation of a complete installed Skill/CLI
workflow, other agent runtimes, or production repositories. This development
split does not authorize a general effectiveness claim. Protocol stays 0.8.

Validate the checked-in normalized evidence and reproduced report without
launching a runtime or grader:

```bash
python3 scripts/check-benchmark-evidence.py \
  --report-file docs/evaluations/benchmark/RESULTS.md
```

Add `--check-current-source` to verify that the current runner/grader source
bytes still match this historical pilot's method hashes. The validator checks
record consistency, not cryptographic runtime attestation or independent
regrading of discarded checkouts.

## Versioned contract corrections

The 0.14 development work keeps the historical `core` suite immutable. Corrected
contracts live under `benchmarks/task-revisions/<task>/v<version>/`, with a
descriptor pinning the original task, fixture, oracle and reference plus the new
public contract, oracle and implementation cases. They are not added to the
original 18-task pilot or used to rewrite its scores.

Run the independent offline check:

```bash
python3 scripts/check-benchmark-contracts.py \
  --task field-ledger-split-export --task-version 2
```

The same entry point also accepts `route-notes-rename-helper` and
`route-notes-no-prose-area` at version 2. Cases may write only files that are both
declared task outputs and supported by the fixture harness; they cannot alter
another task's outputs or overwrite `TASK-CONTRACT.md`.

The checker makes the revision's `public-contract.md` visible as
`TASK-CONTRACT.md` in each constructed checkout. Separate checkouts with
identical input hashes are graded by the v1 and v2 oracles. Its record status
means that the oracle correctly accepted or rejected the stated control case;
it is not an agent task-success score. Raw oracle output is not retained.

Use `--record-dir <new-directory> --report-file <new-report.md>` to retain
append-only, source-bound records and their SHA-256 inventory. Every run checks
the descriptor pins before executing cases and rechecks them before writing
evidence. A failed or unavailable grader stays explicit; it never becomes a
successful contract check. See the [0.14 plan](../docs/MemoryCustodian-v0.14.0-plan.md).

The immutable v1 harness remains separate from the revision validator. As the
revision validator evolves, new records retain method hashes and Git context;
older records retain their original hashes and are reproduced using their
recorded method source, not silently compared as if the method were unchanged.
