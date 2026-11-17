# Benchmark evidence

## Completed development pilot — 2026-11-13

- Package: 0.13.0; Protocol: 0.8; Entry schema: 3.
- Suite: `core`; split: `pilot-development`.
- Tasks: 18 version-1 definitions across the pinned `field-ledger` and
  `route-notes` fixtures.
- Live runtime: Codex CLI `0.167.0-alpha.4.1`, requested model `gpt-6.1-sol`,
  reasoning `low`.
- Completed: all four conditions, 72 independent ephemeral sessions, no
  infrastructure blockers. All 35 PASS and 37 FAIL outcomes are retained.

The [fixed plan](PILOT-2026-11-13.md) records the method and limitations. The
[full report](RESULTS.md) contains the condition summaries, 18 paired outcomes,
failure labels, uncertainty, and the complete matrix. The
[normalized records](runs/pilot-2026-11-13/) retain input/method/runtime hashes,
independent session IDs, observed usage, and sanitized action traces. The source
worktree was modified relative to base commit `e4bcf92`; the exact runner source
hashes, not that base commit alone, identify the evaluated implementation.

The primary comparison is 14/18 for MemoryCustodian and 15/18 for equivalent
manual documents, a paired difference of -5.6 percentage points with a
descriptive 95% task-bootstrap interval of [-16.7, 0.0]. This pilot does not
demonstrate incremental benefit. It is not evidence of general effectiveness,
population equivalence, token savings, or latency improvements.

## Scope and observations

The real subprocess follows each fixture's bootstrap and visible documents;
the MemoryCustodian condition maps `AGENTS.md` to its manifest and brief.
Host skills, plugins, external memories and delegation are disabled uniformly.
This tests the vendored manifest/bootstrap fixture path, not a full installed
Skill/CLI workflow or production repositories. Only Codex ran live; the
separate four-label adapter contract checker remains an offline CLI check.

Observed total input/output tokens, tool-event counts, and runtime durations
are recorded. Authoritative routing completeness, memory-context tokens and
repeated file reads are not measured and remain `null`. Source-path mentions
in normalized action traces do not prove a file was successfully read. Raw
commands, output, prompts, reasoning and machine paths are not retained.

Tasks, fixtures and hidden-oracle rules were not changed in response to these
outcomes. Three tasks failed in both information-matched conditions; one
additional task failed only in MemoryCustodian. These failures are published,
not replaced by known solutions or outcome-driven retries.

## Reproduction and static verification

See [the operator guide](RUNNING-BENCHMARKS.md) for authentication checks,
native runtime flags, generic command adapters, dry runs and validated resume.
Use a fresh repetition ID and record directory for a new sample.

```bash
python3 scripts/run-memory-bench.py --check-integrity
python3 scripts/check-benchmark-evidence.py \
  --report-file docs/evaluations/benchmark/RESULTS.md
```

The first command checks schemas, hashes, isolation, parity, reference
solutions, starter failures and negative solutions. The second checks the 72
normalized records and report rows without launching an agent or grader.
Add `--check-current-source` to verify that the current method source bytes
still match the historical pilot. Static evidence consistency is not
cryptographic runtime attestation or independent regrading of discarded
checkouts. Result records are append-only.

## Claim-bearing expansion

Held-out tasks are not authored. The expansion plan remains 36 paired tasks
across at least three pinned repositories, separate from the development set.
Fix the smallest meaningful effect before collecting claim-bearing data; use
independent repetitions to measure runtime variation. General or named
cross-runtime claims require corresponding held-out live evidence. Publish
inconclusive or negative results when uncertainty or outcomes warrant it.

## Interruption development screen — 2026-11-15

The [fixed interruption plan](INTERRUPTION-2026-11-15.md) and
[results](INTERRUPTION-RESULTS.md) compare fresh restart, an observable progress
summary, and native Codex continuation from six paired interrupted snapshots.
All three conditions passed 4/6 blocks; there were no blockers and no summary
wins over native continuation. This short-task screen does not satisfy the
0.14 checkpoint prerequisites or isolate interruption as the cause of failure.
The existing 0.13 pilot and its method hashes remain unchanged.

## Contract revision controls — 2026-11-16

The [split-export v2 report](CONTRACT-RESULTS.md) records 15/15 offline contract
checks: four positive and eleven negative implementations. V2 accepts different
helper names and checks executed delegation plus preserved export behavior.
The original oracle rejected three positives and accepted eight negatives in
this constructed set. These are new grader controls, not regraded agent runs;
the historical pilot scores remain as recorded.

The [0.14 plan](../../MemoryCustodian-v0.14.0-plan.md) tracks the next contract
reviews and the prerequisites for product-path or checkpoint work.
