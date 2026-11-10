# Offline benchmark harness

This directory is the v0.13 measurement foundation. It does not change Protocol 0.8, Entry schema 3, or the production CLI. A passing integrity check is not evidence that MemoryCustodian improves agent task success, reliability, or token use.

## What a run can answer

The harness prepares the same pinned task under four isolated conditions:

| Condition | What the checkout contains |
|---|---|
| `NO_MEMORY` | Repository code and visible tests. No `docs/memory/`, no `docs/manual/`, and no `AGENTS.md`. |
| `PLATFORM_FILE_ONLY` | A short bootstrap file only. This is an adoption baseline, not an information-matched control. |
| `EQUIVALENT_MANUAL_DOCS` | The same project facts as MemoryCustodian, written as ordinary documents under `docs/manual/`, plus a short map. |
| `MEMORYCUSTODIAN` | Those facts under `docs/memory/`, plus a bootstrap that points at the manifest. `docs/manual/` is removed. |

The primary comparison, once a live pilot exists, is `EQUIVALENT_MANUAL_DOCS` versus `MEMORYCUSTODIAN`. The other two conditions answer different questions and are not the incremental-value comparison.

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

`--mode live` does not launch Codex, Claude Code, Gemini, or a generic agent. It returns status `BLOCKER` and evidence class `live-runtime-unavailable`. A local `--mode command --agent-cmd ...` run is evidence class `command-adapter`. It is not a named-runtime result.

Result files are append-only. The writer uses exclusive create and refuses to overwrite an existing result ID. Pass `--record-dir` only when a normalized record should be kept. Do not commit raw traces. Do not point an agent at the MemoryCustodian checkout; the harness builds a temp checkout that excludes other tasks, hidden oracles, and reference solutions.

## Pilot

Eighteen development-set tasks, nine in `field-ledger` and nine in `route-notes`:

- 6 constraint-sensitive implementation
- 3 architecture / planning
- 3 bug fixing
- 2 refactoring
- 2 history / prior-decision
- 2 stale or conflicting memory

At least half of the tasks depend on a fact that is not stated in the implementation file. Hidden oracles live under `benchmarks/oracles/` and are not copied into the checkout. `MEMORY_CONTEXT_OVERLOAD` is part of the label vocabulary and is not emitted, because this harness does not measure tokens.

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

The schema, task fixtures, offline runner, mechanical grader, four-condition isolation, parity checks, and CI integrity check ship in package 0.13.0. A live runtime has not completed the four conditions. That absence blocks a comparative claim; it does not change Protocol 0.8.
