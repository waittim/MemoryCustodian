# Benchmark evidence

This note records the state of the v0.13 measurement harness. It is not a live agent result and it is not a claim that MemoryCustodian changes task success.

- Date: 2026-11-09
- Package: 0.13.0
- Protocol: 0.8
- Entry schema: 3
- Evidence class: offline fixture integrity
- Suite: `core`
- Split: `pilot-development`
- Tasks defined: 18 across `field-ledger` and `route-notes`
- Live runtimes completed: none

## What was checked

`python3 scripts/run-memory-bench.py --check-integrity` checks the benchmark schema, fixture hashes, four-condition isolation, task-by-task information parity, reference solutions, starter failure labels, and the negative solutions that are pinned. The command does not launch an agent and does not write authoritative project memory.

## What was not run

These conditions have not been executed by Codex, Claude Code, Gemini, or a generic agent:

```text
NO_MEMORY
PLATFORM_FILE_ONLY
EQUIVALENT_MANUAL_DOCS
MEMORYCUSTODIAN
```

No paired comparison, token measurement, or latency measurement exists. Metrics that the harness cannot observe are recorded as null rather than filled in.

## Prespecified comparison

The future primary outcome is `task_success`. The comparison is `EQUIVALENT_MANUAL_DOCS` versus `MEMORYCUSTODIAN`. The analysis unit is the task. The smallest meaningful effect is unset on purpose. Set it before collecting a claim-bearing sample. The 18 pilot-development tasks stay out of that sample.

Held-out tasks are not authored. The expansion target remains 36 paired tasks across 3 repositories. That target is a planning floor, not a result.

## Reproduction

From a clean checkout:

```bash
python3 scripts/run-memory-bench.py --check-integrity
python3 scripts/run-memory-bench.py \
  --suite core \
  --runtime codex \
  --condition MEMORYCUSTODIAN \
  --dry-run
```

The dry run prints prompt and visible-source hashes. It does not write a result file. `--mode live` returns `BLOCKER` until a real runtime adapter exists.
