# Development interruption experiment results

Generated: 2026-11-15T10:00:49.095127+00:00
Runtime: codex-cli 0.169.0-alpha.11.1; requested model: gpt-6.1-sol; reasoning: low.

Development fixtures only; no general effectiveness or long-horizon claim.

| Task | Repetition | Block | FRESH | OBSERVABLE_CHECKPOINT | NATIVE_RESUME |
| --- | --- | --- | --- | --- | --- |
| field-ledger-rounding | 1 | COMPLETE | PASS | PASS | PASS |
| field-ledger-rounding | 2 | COMPLETE | PASS | PASS | PASS |
| field-ledger-split-export | 1 | COMPLETE | FAIL | FAIL | FAIL |
| field-ledger-split-export | 2 | COMPLETE | FAIL | FAIL | FAIL |
| route-notes-redact-secrets | 1 | COMPLETE | PASS | PASS | PASS |
| route-notes-redact-secrets | 2 | COMPLETE | PASS | PASS | PASS |

Complete three-condition pairs: 6/6.

| Condition | PASS / valid pairs | Mean tools | Mean input tokens | Mean output tokens | Mean seconds |
| --- | --- | --- | --- | --- | --- |
| FRESH | 4/6 | 5.3 | 86747.8 | 1017.3 | 32.6 |
| OBSERVABLE_CHECKPOINT | 4/6 | 6.5 | 96879.5 | 1045.3 | 33.7 |
| NATIVE_RESUME | 4/6 | 4.8 | unobserved | unobserved | 29.9 |

## Gate interpretation

Native continuation failures in valid pairs: 2. Observable-summary wins over native: 0.
BLOCKER and inapplicable samples are excluded from success comparisons.
Repeated file reads are unobserved (null); tool events do not prove repeated reads.
The checkpoint condition is an experimental observable-metadata summary, not the proposed production feature.
The boundary is early (two completed tools), not representative long-horizon interruption.
A small development screen cannot establish material production failures or checkpoint benefit; the 0.14 gate remains unproven.
No shared protocol, authoritative routing, or durable project memory is changed by a runtime.

## Reproduction and evidence

See [the fixed plan](INTERRUPTION-2026-11-15.md). Append-only per-pair JSON and experiment.json
record exact method/plan hashes, common-prefix session IDs, identical starting-tree hashes,
interruption event counts, oracle outcomes, and post-resume metrics. Raw traces are not published.
Native session history uses the CLI's normal local session store; this runner neither copies credentials nor exports that history.
Token/time means describe recovery turns only, excluding common-prefix cost; no savings or latency claim follows.
Native CLI usage is session-cumulative; its raw counters are retained separately and post-resume tokens stay null because no interrupted-prefix baseline is available.
Do not tune these fixtures from outcomes; any follow-up sample needs a new plan and record directory.

## Observed conclusion and limits

All six prescribed interruptions were verified with two unique completed tool
events, a live process at termination, and signal exit `-15`. Every recovery
condition started from its block's identical snapshot; all 18 recovery turns
completed, all native resumes preserved their prefix session ID, and fixture
memory stayed unchanged. There were no infrastructure blockers, invalid
interruptions, or already-solved prefixes. The formal sample comprises six
common-prefix invocations and 18 recovery invocations; availability preflights
are excluded.

Each condition passed 4/6 blocks. Both repetitions of `field-ledger-split-export`
failed the hidden oracle under all three conditions while passing the visible
tests. The other two tasks passed under all three conditions in both repetitions.
The observable summary produced zero success improvements over either fresh
restart or native continuation in this sample.

This experiment has no concurrent uninterrupted control, so the two native
failures cannot be attributed to interruption. The same task also failed in both
information-matched conditions of the [earlier pilot](RESULTS.md), which used
a different CLI version and is not a causal control for this experiment.
These short development tasks, an early interruption boundary, and a minimal
observable-summary prototype do not establish the behavior of longer tasks or
a fuller checkpoint design. They also do not prove equivalence or that
checkpointing is generally useless.

**The current sample does not satisfy the 0.14 checkpoint prerequisites.**
There is no observed success benefit beyond native continuation and no isolated
evidence of a material interruption-specific failure. Keep checkpointing
conditional; investigate the shared task failure before attributing it to
resume, and use a separately fixed plan with longer tasks and an uninterrupted
control if further checkpoint evaluation is justified.

Local validation: the complete unittest suite exited successfully; all 12 new
interruption-harness tests passed. Existing fixture integrity and all 72 original
pilot evidence records passed their static checks. These harness checks support
record consistency, not an agent-effectiveness claim.
