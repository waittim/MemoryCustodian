# Fixed observer-correction follow-up — 2026-11-17

This is one new independent sample of the original `unconfirmed-observation`
task after correcting an independently reproducible observer defect. It is not
a retry under unchanged scoring to replace an unfavorable result.

## Prior evidence remains intact

Preserve the original three-task sample under
`installed-skill-live-2026-11-16/` and the two-task diagnostic sample under
`installed-skill-live-diagnostic-2026-11-17/`, including the latter candidate
task's recorded FAIL. Do not regrade or relabel either cohort.

The diagnostic candidate run passed its artifact and strict-read-content checks
but failed ordering because a possible-mutation event preceded its complete
strict maintenance read. The early command's raw payload was not retained.
Its hash has not established that it was help, a preview, or an actual write;
the cause of that particular failure remains unresolved. Existing help-output
hash probes do not establish the early command's identity.

The former method is retained in Git commit
`d125910bc54866b2dc77a71fc6730b676f748f03`; its five method SHA-256 values were
verified against the diagnostic experiment before this correction. The original
16th-day method also has its existing exact source snapshots. New source hashes
identify the corrected observer and this plan, rather than rewriting old pins.

## Independently reproduced observer defect

Observer schema 1 marked a command as a possible mutation whenever it contained
the installed CLI path and a mutation-like word such as `add`. Grading treated
the earliest possible event as a definite write. Thus a valid single CLI
`add --help` or a non-applied `subject add` preview could falsely fail ordering.
Offline controls use the real installed CLI's help and preview output to
demonstrate the mismatch independently of any live command's unknown payload.

Observer schema 2 retains `mutation_sequences` as the original possible lexical
events. It adds confirmed and uncertain mutation sequences, verified read-only
CLI sequences, and an explicit schema version. A narrow classifier recognizes
only a single direct installed-CLI invocation, optionally wrapped in one known
shell `-c`/`-lc` call. Compound commands, redirection, substitution, multiline
programs, variable/glob/brace/tilde expansion, comments and unrecognized forms are not
declared read-only. Option terminators and abbreviated flags are not used to
certify a preview; recognized options accept their full name and `--name=value`
form. All installed-CLI starts remain uncertain until classified, including
unknown commands whose names do not match the original mutation-word heuristic.

Single successful CLI help is read-only. Known non-applied preview forms require
the real versioned JSON envelope and public-plan schema alongside the parsed
single-call arguments. A plan's presence alone does not prove a preview, and no
unexposed phase field is invented. Successful direct `add` and applied Subject
creation can establish a write attempt; file-change events also establish write
attempts. Only allowlisted action categories and public-plan presence are
retained, never raw arguments or output.

A confirmed write before a complete strict read still fails. If ordering rests
on an early uncertain event, or no bounded write event can be established, an
otherwise conforming result is REVIEW rather than an invented PASS or FAIL.
Artifact failures remain FAIL. Help followed by another shell write is not
granted a read-only exemption. This is finite observation, not a general shell
interpreter or adversarial attestation system.

Required offline controls before collection:

- Real single-call help and Subject preview, then strict read, then actual
  candidate writing pass the ordering check.
- Actual candidate writing before the strict read still fails.
- Help combined with a subsequent shell write cannot pass by being mistaken
  for a single read-only help invocation.
- Ambiguous early possible writes produce REVIEW when other checks conform.
- The old possible-event field retains its meaning and raw-payload exclusions.

## Fixed new sample

Run only `unconfirmed-observation`, once, in a fresh independent ephemeral
session. Do not rerun the already valid scoped and missing-scope tasks. The task,
prompt, fixture construction, allowed writes, candidate/artifact requirements,
model `gpt-6.1-sol`, reasoning `low`, 180-second budget, manual installed Skill
invocation, sandbox and privacy boundaries remain unchanged. Only observer
classification and its ordering evidence are corrected.

Freeze/commit this method before execution. Preserve any PASS, FAIL, REVIEW or
BLOCKER from the new sample without an outcome-based retry loop. Runtime
unavailability remains BLOCKER; unit stubs remain offline. Report all earlier
outcomes alongside this separate sample, without claiming that the old FAIL
has been explained or disproved, or presenting a replacement first-attempt
3/3 score. No comparative effectiveness or automatic-discovery claim follows.

## Reproduction

```bash
python3.13 scripts/run-installed-skill-eval.py \
  --codex-executable codex --model-version gpt-6.1-sol \
  --tasks unconfirmed-observation \
  --record-dir docs/evaluations/installed-skill-live-observer-2026-11-17 \
  --report-file docs/evaluations/INSTALLED-SKILL-LIVE-OBSERVER-RESULTS-2026-11-17.md
```

Use new append-only output paths. Earlier source snapshots, records, plans and
their recorded hashes remain unchanged; a new result does not revise them.
