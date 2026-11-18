# Fixed interruption feasibility plan — 2026-11-15

This plan fixes a development experiment before collecting its results. Its
purpose is to test whether the available runtime can resume interrupted work and
whether an observable checkpoint summary warrants further investigation for
0.14. It is not a production checkpoint implementation, a representative
long-horizon task suite, or a claim-bearing evaluation.

The existing 0.13 pilot, tasks, fixtures, reference solutions, oracles, and source
hashes remain unchanged. Results from this experiment are recorded separately.
Shared Protocol remains 0.8 and Entry schema remains 3.

## Fixed sample and settings

- Tasks: version 1 of `field-ledger-split-export`, `field-ledger-rounding`, and
  `route-notes-redact-secrets`, using the existing pinned fixtures and the
  `MEMORYCUSTODIAN` condition's visible source tree.
- Repetitions: two independent common prefixes per task, for six attempted
  interrupted blocks. Do not replace invalid blocks or tune tasks or boundaries
  after inspecting outcomes.
- Runtime: real Codex CLI, requested model `gpt-6.1-sol`, reasoning `low`.
  Record the actual CLI version and method-source hashes. A model identifier
  may be a server alias; this sample does not establish cross-version behavior.
- Permissions: workspace-write, agent shell network disabled, approval `never`;
  host skill discovery, bundled skills, plugins, apps, memories, web search, and
  delegation disabled. Use the existing runtime authentication without copying
  credentials into fixtures or published records.
- Budget: 180 seconds for the common prefix and 180 seconds for each recovery
  invocation. Do not change a condition's budget based on its outcome.
- Isolation: temporary checkouts outside the project. Hidden grading and
  reference solutions remain outside the agent-visible checkout. No commit,
  publication, or authoritative project-memory mutation is part of the task.

## Common prefix and forced interruption

For each task/repetition, execute exactly one fresh common prefix. Consume its
JSONL events and terminate the complete runtime process group immediately after
the **second completed `command_execution` or `file_change` tool event**. Count
each tool ID once; the event boundary is fixed independently of its command,
exit status, or apparent usefulness. Do not wait for a successful task outcome or
choose a later, more favorable boundary.

After stopping and reaping the process group, capture the interrupted checkout
snapshot and its fingerprint. All three recovery conditions must receive this
same snapshot. Before every condition, reset the checkout to those bytes at the
same path. Preserve the prefix's native session identity for the native-resume
condition, without exposing that session history to fresh conditions.

If the prefix never reaches the boundary, record an invalid interruption. If
the task is already complete at the boundary, record an inapplicable block.
Neither is a resumed-task failure; retain its reason and exclude the block from
paired recovery comparisons. Authentication, runtime, or native-resume
unavailability is a `BLOCKER`, not an experimental task failure.

## Recovery conditions

Every condition receives the original task and starts from the same interrupted
checkout. Rotate the three-condition order across the six attempted blocks.
No outcome-based retries or replacement samples are allowed.

| Condition | Additional recovery context |
| --- | --- |
| `FRESH` | A fresh session with the original task and interrupted checkout. |
| `OBSERVABLE_CHECKPOINT` | A fresh session with the same inputs plus the bounded observable summary below. |
| `NATIVE_RESUME` | Resume the prefix's original native session against the restored checkout. |

The experimental checkpoint may contain only observable, non-reasoning agent
messages, completed tool types and exit statuses, and relative file changes and
hashes. It must not retain raw tool output, raw command arguments, environment
variables, hidden reasoning, or oracle answers. Do not infer a successful read
from a path mention, or a successful test from an intended command. The summary
does not grant permission to replay commands or external actions.

This summary tests the potential value of bounded execution context. It does
not validate a production task-state schema, writer, retention policy, crash
recovery mechanism, stale-state classifier, concurrent-writer policy, or privacy
and deletion contract.

## Outcomes and reporting

The primary outcome is resumed task success: both the task's existing visible
tests and hidden mechanical oracle must pass. Grade only after the recovery
runtime has stopped. Preserve failures and infrastructure outcomes separately.

Report, for every attempted block and recovery condition:

- interruption eligibility and the reason for invalid or inapplicable blocks;
- runtime completion, blockers, visible-test result, and oracle result;
- post-resume tool-call counts, observed input/output tokens, and elapsed time;
- snapshot, prompt, method-source, and relevant event-stream hashes;
- checkpoint-summary availability and native-resume availability.

Repeated file reads cannot be reliably measured from the current event
metadata and remain `null`. Missing token usage also remains `null`; do not
convert unavailable observations to zero. A preflight of the current CLI
observed session-cumulative token usage on native resume. Since an interrupted
prefix has no completed-turn usage baseline, retain the runtime-reported totals
separately and mark native post-resume token counts `null`; do not compare those
cumulative totals with fresh-session recovery tokens. Token and timing differences are
descriptive observations, not causal cost or latency claims. Keep raw outputs,
command arguments, hidden reasoning, credentials, and machine paths out of the
published normalized records.

## Prespecified interpretation

- This small development sample cannot establish general effectiveness,
  statistical equivalence, production safety, or a material long-horizon gain.
- If native continuation shows no evident failure on eligible blocks, this
  sample does not support adding a checkpoint capability beyond native resume.
- An observed checkpoint advantage is a reason to investigate with additional,
  independently designed tasks and repetitions; it does not by itself satisfy
  the production feature's release gates.
- An unavailable native-resume condition is a `BLOCKER`. It cannot count as a
  native failure or a checkpoint victory.
- Without valid interrupted paired blocks, the result is insufficient to
  evaluate the 0.14 checkpoint prerequisites. Publish that limitation rather
  than treating lack of observations as success or failure.

## Reproduction

Use a logged-in compatible Codex CLI and a fresh record directory. Record the
source hashes before collection and retain each result append-only. A rerun is
a new sample, not a replacement for an earlier outcome.

```bash
python3 scripts/run-interruption-bench.py \
  --codex-executable codex \
  --model-version gpt-6.1-sol \
  --record-dir docs/evaluations/benchmark/runs/interruption-2026-11-15 \
  --report-file docs/evaluations/benchmark/INTERRUPTION-RESULTS.md
```
