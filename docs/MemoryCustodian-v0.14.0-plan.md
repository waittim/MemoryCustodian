# MemoryCustodian v0.14.0 development plan

Status: In progress; WP14A completed and locally validated.

Started: 2026-11-16.

Target: Evidence-backed reliability and evaluation-contract improvements.
Compatibility: Shared Protocol 0.8; Entry schema 3. Package version is not bumped
by this work package, and this document is not a release announcement.

## Scope decision

Use the reliability fallback permitted by the [pre-1.0 roadmap](MemoryCustodian-v0.13-to-v1.0-roadmap.md#51-theme).
The [interruption experiment](evaluations/benchmark/INTERRUPTION-RESULTS.md)
produced 4/6 successes in each recovery condition and zero observable-summary
wins over native continuation. It did not isolate a material interruption-specific
failure or establish checkpoint benefit. Keep production checkpointing deferred;
this small sample does not establish that checkpointing is generally useless.

Start by making benchmark contracts assess the behavior they publicly require.
An oracle false rejection or false acceptance is an evaluation defect; a failed
fixture task alone does not establish a production Skill or CLI defect.

## WP14A — Versioned split-export contract

Status: Completed on 2026-11-16. The [offline report](evaluations/benchmark/CONTRACT-RESULTS.md)
records 15/15 contract checks: four conforming implementations and eleven
nonconforming controls. The v1 oracle rejected three positives and accepted
eight negatives in that constructed set. These are grader controls, not revised
historical agent outcomes.

The version-1 oracle for `field-ledger-split-export` checks for the text
`export_entries` in `ledger.py`, the existence of `export.py`, and a two-row
result. That can reject a correct refactor using another helper name and can
accept a placeholder module plus a matching comment while export remains in
`ledger.py`.

Deliver an independent task revision **2** with:

- A versioned descriptor, an agent-visible contract, a behavioral oracle, and
  positive and negative implementation cases.
- A public contract stating that `export.py` owns construction of the returned
  row list and application of the existing export cap; `Ledger.export()`
  delegates that responsibility. Helper names and equivalent import styles are
  free choices.
- Explicit preservation of row contents and order, a new outer list with the
  existing shallow-copy behavior, and existing cap behavior (`None` returns all
  rows; other supported values retain the existing slice semantics). These
  requirements must appear in the visible revision-2 contract before grading.
- Positive cases for valid delegation with different helper names and equivalent
  implementations; negative cases for a placeholder module, a comment-only
  symbol match, responsibility left in `ledger.py`, and changed export results.
- A separate, standard-library offline validator:
  `scripts/check-benchmark-contracts.py`. It records the revision, case outcomes,
  and source hashes in new append-only evidence records and a separate report.

Acceptance gates:

- [x] Every specified conforming control passes with its supported helper names
  and import styles.
- [x] Every specified nonconforming control fails for its stated reason.
- [x] Revision-2 requirements are visible and do not depend on undisclosed
  reference-implementation details.
- [x] The independent validator emits source-bound records and a report, and
  refuses to overwrite existing records.
- [x] Relevant automated tests pass; original fixture integrity and historical
  evidence consistency checks still pass.
- [x] The original 18 task definitions, fixtures, oracles, runner sources, and
  recorded pilot/interruption hashes remain unchanged. Do not regrade the
  original agent results under revision 2.

Offline reproduction (use new paths for another retained sample):

```bash
python3 scripts/check-benchmark-contracts.py \
  --task field-ledger-split-export \
  --task-version 2 \
  --record-dir docs/evaluations/benchmark/runs/contracts-2026-11-16 \
  --report-file docs/evaluations/benchmark/CONTRACT-RESULTS.md
```

This checks the grader's contract against implementation cases. It is not a new
live-agent result or evidence of improved task success.

Validation: 562 unittest cases passed, including 16 new oracle/revision checks.
The original 18-task fixture integrity, 72-record pilot evidence with current
method hashes, skill/adapter contracts, erasure wording, and version checks
passed locally. The revision checker is included in the Linux and Windows CI
matrices; remote CI and other local Python/OS combinations have not been run.

## WP14B — Review adjacent evaluation contracts

Status: Planned; each finding requires independent confirmation.

First inspect `route-notes-rename-helper` for syntax-specific acceptance and
`route-notes-no-prose-area` for rejection caused by explanatory text. Then
consider string-specific rejection in `field-ledger-offline-plan` and accidental
acceptance of constant answers in `route-notes-token-estimate`.

For each confirmed defect, write the public behavioral contract, demonstrate
both a conforming and nonconforming case, and add a separate task revision and
new evidence. Preserve historical definitions and outcomes. Any new live-agent
comparison needs its own fixed plan and sample; do not tune the old sample to
increase its success rate.

## WP14C — Reproduce product failures through installed workflows

Status: Conditional on diagnostic evidence.

Exercise a fully installed Skill/CLI path before assigning a benchmark failure
to the production product. Record the exact installation, runtime, task, scoped
inputs, expected behavior, and minimal reproduction. Fix a demonstrated product
defect with a regression check appropriate to the affected behavior. Keep
evaluation defects, fixture limitations, and product defects distinct in the
result report.

## WP14D — Revisit checkpoint evidence if a resume gap emerges

Status: Deferred; requires a concrete failure hypothesis.

If further investigation justifies it, fix a new plan using longer tasks and an
uninterrupted control alongside fresh restart, observable checkpoint, and native
continuation. Preserve paired starting state, runtime settings, and failure
accounting. Native unavailability remains a blocker. A production checkpoint
feature still requires the roadmap's safety and privacy gates in addition to
evidence of incremental value.

## Completion and release gates

WP14A has checked offline evidence; the next work package is WP14B. Mark later work
packages as deferred when their prerequisites are absent; they are not all
mandatory release features. Before any 0.14 release, identify the work actually
shipped, pass its relevant checks and repository-required tests, retain the
historical evidence, and keep public claims within the measured scope.

This development work does not authorize a package-version bump, tag, or release.
