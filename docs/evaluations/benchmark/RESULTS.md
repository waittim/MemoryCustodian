# Memory Benchmark Evaluation Report

- Generated: 2026-11-14T06:20:47.574201+00:00
- Runtime: `codex`
- Model version: `gpt-6.1-sol`
- Tasks evaluated: 18
- Conditions: `NO_MEMORY`, `PLATFORM_FILE_ONLY`, `EQUIVALENT_MANUAL_DOCS`, `MEMORYCUSTODIAN`
- Evidence boundary: pilot-development results are descriptive; no comparative effectiveness claim.

## 1. Condition Summary

| Condition | Total | PASS | FAIL | BLOCKER | REVIEW | Success Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `NO_MEMORY` | 18 | 3 | 15 | 0 | 0 | 16.7% |
| `PLATFORM_FILE_ONLY` | 18 | 3 | 15 | 0 | 0 | 16.7% |
| `EQUIVALENT_MANUAL_DOCS` | 18 | 15 | 3 | 0 | 0 | 83.3% |
| `MEMORYCUSTODIAN` | 18 | 14 | 4 | 0 | 0 | 77.8% |

## 2. Primary Paired Comparison (EQUIVALENT_MANUAL_DOCS vs MEMORYCUSTODIAN)

- **Total paired tasks**: 18
- **Both PASS**: 14 (77.8%)
- **Both FAIL**: 3 (16.7%)
- **MEMORYCUSTODIAN only PASS**: 0
- **EQUIVALENT_MANUAL_DOCS only PASS**: 1
- **Incomplete pairs excluded**: 0 (missing, BLOCKER, or REVIEW)
- **Paired success-rate difference (MC − manual)**: -5.6 percentage points
- **95% paired bootstrap interval**: [-16.7, 0.0] percentage points
- Uncertainty method: paired task bootstrap, 10000 resamples, seed 0; descriptive pilot only.
- This resamples the observed tasks, not new repositories or independent runtime repetitions. Small, related fixture tasks and one repetition cannot establish a general benefit.

## 3. Failure Label Distribution

| Condition | Failure Labels |
| :--- | :--- |
| `NO_MEMORY` | `MEMORY_CONFLICT_MISSED`: 2, `MEMORY_OMISSION`: 11, `MEMORY_STALE_USE`: 2 |
| `PLATFORM_FILE_ONLY` | `MEMORY_CONFLICT_MISSED`: 2, `MEMORY_OMISSION`: 11, `MEMORY_STALE_USE`: 2 |
| `EQUIVALENT_MANUAL_DOCS` | `MEMORY_OMISSION`: 3 |
| `MEMORYCUSTODIAN` | `MEMORY_OMISSION`: 4 |

## 4. Task Outcome Matrix

| Task ID | `NO_MEMORY` | `PLATFORM_FILE_ONLY` | `EQUIVALENT_MANUAL_DOCS` | `MEMORYCUSTODIAN` |
| :--- | :---: | :---: | :---: | :---: |
| `field-ledger-closed-ledger` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS |
| `field-ledger-conflicting-cap` | ❌ MEMORY_CONFLICT_MISSED | ❌ MEMORY_CONFLICT_MISSED | ✅ PASS | ✅ PASS |
| `field-ledger-currency` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION |
| `field-ledger-export-cap` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |
| `field-ledger-offline-plan` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |
| `field-ledger-reject-negative` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |
| `field-ledger-rounding` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |
| `field-ledger-split-export` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION |
| `field-ledger-superseded-cap` | ❌ MEMORY_STALE_USE | ❌ MEMORY_STALE_USE | ✅ PASS | ✅ PASS |
| `route-notes-budget-conflict` | ❌ MEMORY_CONFLICT_MISSED | ❌ MEMORY_CONFLICT_MISSED | ✅ PASS | ✅ PASS |
| `route-notes-manifest-only` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS |
| `route-notes-no-prose-area` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ❌ MEMORY_OMISSION |
| `route-notes-redact-secrets` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |
| `route-notes-rename-helper` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS |
| `route-notes-skip-archive` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION |
| `route-notes-storage-choice` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |
| `route-notes-superseded-load-all` | ❌ MEMORY_STALE_USE | ❌ MEMORY_STALE_USE | ✅ PASS | ✅ PASS |
| `route-notes-token-estimate` | ❌ MEMORY_OMISSION | ❌ MEMORY_OMISSION | ✅ PASS | ✅ PASS |


## 5. Provenance and reproduction

- Client-local run date: 2026-11-13 (America/Los_Angeles); the generated UTC
  timestamp above is the same date's evening in that timezone.
- Plan and command: [fixed pilot settings](PILOT-2026-11-13.md).
- Evidence: [72 append-only normalized records](runs/pilot-2026-11-13/) and
  their [SHA-256 inventory](runs/pilot-2026-11-13/SHA256SUMS).
- CLI: `codex-cli 0.167.0-alpha.4.1`; requested model: `gpt-6.1-sol`; reasoning:
  `low`; one independent ephemeral session per cell; 180-second time budget;
  no explicit token cap; four concurrent sessions; balanced condition order.
- Every record has evidence class `live-runtime`, a different session ID,
  exactly one successful turn-completion event, and CLI exit code zero before
  grading. There were no missing cells, runtime blockers, or outcome retries.
- Base Git commit: `e4bcf922f46bccd2f66bf15e0eaf574a0157c501`; `git_dirty: true`.
  Uncommitted implementation changes are identified by the exact source-byte
  hashes below. All 72 records share this method hash mapping.

| Evaluated source | SHA-256 |
| --- | --- |
| `benchmarks/graders/mechanical.py` | `228586fa06c1b7c65b8e10dd01eb2b86bc6c03005610c591c177db276718d234` |
| `benchmarks/runners/codex_runtime.py` | `0735c9cd3d9fbcce264e27cfbc7c853e5a90fd75ebe0c5b8e9baec0abc9c4dc7` |
| `benchmarks/runners/harness.py` | `8907a1ab2d254d8813a8677f46c1babe6e1073c7a68fcaf72ffc40e3382b2007` |
| `scripts/run-batch-benchmark.py` | `1a46ea736e3c7371a7703b3186f1ad8d28bfe9632ea6c71a7119b93d5e396595` |

Validate inputs and reproduce the normalized report comparison without running
an agent:

```bash
python3 scripts/run-memory-bench.py --check-integrity
python3 scripts/check-benchmark-evidence.py --check-current-source \
  --report-file docs/evaluations/benchmark/RESULTS.md
```

The validator is a static consistency check: it cannot authenticate the event
hashes or independently regrade the deleted temporary checkouts. PASS relies
on the frozen harness's visible-test plus hidden-oracle gate. Rerunning the
live command in the plan with a new repetition produces a new sample; it does
not overwrite these records.

## 6. Interpretation and next evaluation

The primary comparison has one discordant task, `route-notes-no-prose-area`,
where equivalent manual documents passed and MemoryCustodian failed. Both
conditions failed `field-ledger-currency`, `field-ledger-split-export`, and
`route-notes-skip-archive`. No reference solution was substituted for a failed
agent run, and no task, fixture, or oracle was tuned on these outcomes.

This is a single development pilot on small, purpose-built text fixtures.
The MemoryCustodian condition exercises its fixture's manifest/bootstrap path;
host skills and plugins are disabled uniformly, and this is not validation of
a full installed Skill/CLI workflow. Checkouts are outside the repository and
omit hidden grading/solution files, but sandbox/prompt confinement is not an
adversarial read jail. The fixtures are not initialized Git repositories.
Only Codex ran live; model identifiers can be server aliases, and this sample
cannot establish other-runtime or production-workload behavior.

The empirical paired bootstrap resamples the 18 observed tasks, not independent
repositories or runtime repetitions. Boundary intervals or zero-width intervals
must not be interpreted as evidence of population equivalence. The observed
negative difference does not establish general harm or improvement. These
results authorize no comparative effectiveness claim.

Total token usage, tool-event counts and execution times are observations, not
memory-specific cost estimates or latency improvements. Prompt caching,
concurrent sessions and startup overhead are uncontrolled for those secondary
measurements. Routing completeness, memory-context tokens and repeated file
reads remain null. Normalized action traces retain source-path mentions,
operation statuses and hashes; mentions do not prove successful reads, and
failed tool operations cannot be causally attributed without raw traces.

Before a claim-bearing evaluation, author at least 36 held-out paired tasks
across three pinned repositories, include a fully installed workflow, fix the
smallest meaningful effect and analysis before collection, and run independent
repetitions. Keep these development outcomes out of that sample and publish
negative or inconclusive results as such.
