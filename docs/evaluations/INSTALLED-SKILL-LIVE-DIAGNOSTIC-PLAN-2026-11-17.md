# Fixed installed-Skill diagnostic follow-up — 2026-11-17

This is a new, independent infrastructure-diagnostic sample after the initial
three-task installed-Skill smoke. Preserve its original plan and every original
record under `docs/evaluations/installed-skill-live-2026-11-16/` unchanged.

The initial sample completed `scoped-implementation` with PASS. `missing-scope`
and `unconfirmed-observation` each ended with runtime exit 1 and zero successful
turn completions, so both remain infrastructure BLOCKER outcomes. Their raw
runtime errors were not retained; hashes alone cannot recover or establish the
original causes. Do not relabel those records from later observations.

## Fixed selection and unchanged acceptance

Execute exactly one new independent session for each of:

- `missing-scope`
- `unconfirmed-observation`

Do not repeat the already valid `scoped-implementation` PASS. This follow-up
retries only the two tasks that produced no valid completed task result; it is
not an outcome-based retry of a scored task failure. Retain this sample in a
new directory, including new failures or blockers. Do not replace, overwrite,
or hide the initial cohort, and do not tune tasks from new outcomes.

Task text, invocation instructions, fixture construction, scope/write limits,
mechanical checks and grading rules remain identical to the original
[fixed plan](INSTALLED-SKILL-LIVE-PLAN-2026-11-16.md). The original method's three
mutable source files have exact hash-matched snapshots in the original record
directory's `method-snapshot/`; the unchanged frozen Codex helper remains
identified by its original recorded SHA-256. New method hashes identify only
added diagnostic observation and explicit task selection. Historical results
retain the method that actually produced them.

Runtime remains real Codex CLI, model `gpt-6.1-sol`, reasoning `low`, 180 seconds
per task, sequential independent ephemeral sessions. Keep the same sandbox,
manual installed-Skill invocation, existing authentication, private temporary
state, disabled agent-shell network, approval `never`, and disabled external
plugins/memories/web/delegation. Do not change `HOME`, `CODEX_HOME`, global
installation, configuration or authentication. There is no extra live preflight
task and no outcome-based retry loop in this follow-up.

## Added diagnostic observations

Inspect error payloads only in memory. Retain diagnostic schema 1 with:

- Counts of fixed, allowlisted event kinds; unknown kind strings become `other`.
- Error/turn-failure event order, allowlisted statuses, numeric HTTP statuses,
  and numeric process exit status. The error-event list is bounded at 32.
- Coarse hints `transport`, `auth`, `rate-limit`, `provider`, or `unknown`.
  Local failures may additionally report `timeout`, `encoding`, or `launch`.
- Presence of stderr and allowlisted category hints. No raw stderr, error
  message, provider-specific code string, URL, header, request identifier,
  credential, prompt, command, output, reasoning or machine path is retained.
- For timeouts, only hashes and diagnostics from already captured partial
  output, clearly labelled as a partial capture. Missing output stays missing.

These are coarse observations, not authenticated provider assertions or a
confirmed root-cause diagnosis. Unknown errors remain unknown. Diagnostic
collection does not convert an incomplete runtime into a task PASS or FAIL:
runtime unavailability still produces BLOCKER, and unit stubs remain offline.

## Interpretation and evidence

Report this two-task sample separately. Link the initial three-task cohort and
preserve its one PASS and two BLOCKER outcomes. If both follow-up tasks complete,
describe their observed outcomes; do not present a replacement 3/3 first-attempt
success rate or discard infrastructure failures. A repeated error category
supports investigation, not automatic attribution to a product defect.

The controller keeps append-only UTF-8/LF records, source/fixture/prompt hashes,
unique session identities and completion evidence. `--tasks` records the exact
selected subset; omitted tasks do not become successes. Freeze/commit the new
method before execution and use new output paths for any further sample.

## Reproduction

```bash
python3.13 scripts/run-installed-skill-eval.py \
  --codex-executable codex --model-version gpt-6.1-sol \
  --tasks missing-scope unconfirmed-observation \
  --record-dir docs/evaluations/installed-skill-live-diagnostic-2026-11-17 \
  --report-file docs/evaluations/INSTALLED-SKILL-LIVE-DIAGNOSTIC-RESULTS-2026-11-17.md
```

No live result is claimed by this plan or its offline unit tests. Automatic
Skill discovery, comparative effectiveness and cross-runtime conformance remain
outside the original smoke and this diagnostic follow-up.
