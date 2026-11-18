# MemoryCustodian v0.14.0 candidate readiness

Updated: 2026-11-17. Status: validated candidate for release review; not published.

The proposed release improves evaluation contracts and verification reliability.
It does not change production memory semantics, authoritative routing, or the
shared protocol. Candidate package: **0.14.0**; Protocol: **0.8**; Entry schema:
**3**. See the [work plan](MemoryCustodian-v0.14.0-plan.md).

## Reviewable scope

Five independent revision-2 contracts replace syntax- or wording-specific checks
with publicly described acceptance rules. They cover split-export delegation,
selection-helper delegation, standalone area-plan actions, offline-plan prose
and bounded client-import checks, and whitespace token estimation. The revised
contracts and their finite implementation controls retain separate identities;
historical tasks and real agent outputs are not regraded.

| Contract | Constructed controls | Recorded status |
| --- | --- | --- |
| [split-export](evaluations/benchmark/CONTRACT-RESULTS.md) | 15 | PASS |
| [rename-helper](evaluations/benchmark/CONTRACT-RENAME-HELPER-RESULTS.md) | 19 | PASS |
| [area-plan](evaluations/benchmark/CONTRACT-AREA-PLAN-RESULTS.md) | 23 | PASS |
| [offline-plan](evaluations/benchmark/CONTRACT-OFFLINE-PLAN-RESULTS.md) | 13 | PASS |
| [token-estimate](evaluations/benchmark/CONTRACT-TOKEN-ESTIMATE-RESULTS.md) | 19 | PASS |

All **89** constructed contract controls match their expected outcomes. The
latest two revisions have 32 new formal records. These are offline grader
checks, not live-agent task successes or held-out effectiveness evidence.

## Gate status

| Gate | Current status | Evidence or remaining action |
| --- | --- | --- |
| Public contracts and independent records | PASS | Five versioned contracts and 89 matching controls above; preserve public requirements and source hashes. |
| Historical evidence preservation | PASS | Original [0.13 pilot](evaluations/benchmark/RESULTS.md): 72 sessions. Original [interruption screen](evaluations/benchmark/INTERRUPTION-RESULTS.md): six paired blocks. Their definitions, methods, and outcomes remain unchanged. |
| Local installed CLI workflow | PASS, local scope | Isolated installed-CLI smoke passed. This does not establish automatic Skill discovery or general agent behavior. |
| Full local unittest suite | PASS | 605 tests passed on 2026-11-17 after observer correction (`8f0bbe1`). Skill/adapter contracts, fixture integrity, historical evidence, version, erasure language, memory security/privacy and audit checks also passed. |
| Initial installed-Skill live sample | PARTIAL | 2026-11-16: one PASS, two infrastructure BLOCKER outcomes; see the separate evidence below. |
| Diagnostic follow-up | COMPLETE, mixed | The independent two-task sample recorded missing-scope PASS and unconfirmed-observation FAIL; preserve both outcomes. |
| Observer correction and independent sample | PASS, bounded | 14 observer tests passed, including real CLI controls. One new candidate-task session passed under the separately fixed method `8f0bbe1`; see the [result](evaluations/INSTALLED-SKILL-LIVE-OBSERVER-RESULTS-2026-11-17.md). |
| Remote compatibility CI | PASS | All ten Linux/Windows × Python 3.10–3.14 jobs passed for implementation commit `8f0bbe1`: [CI run 44157617701](https://github.com/waittim/MemoryCustodian/actions/runs/44157617701). The [record](evaluations/CI-CANDIDATE-RESULTS-2026-11-17.json) pins that SHA and each job. Subsequent evidence-only commits receive their own branch CI. |
| Reproducible distribution builds | PASS, payload pinned | ZIP and tar.gz each reproduced byte-for-byte from `d125910`; both extracted runtimes passed strict routing, check and audit. The packaging script and all payload paths remain unchanged through `8f0bbe1` and current documentation-only updates. See the [build record](evaluations/PACKAGE-BUILD-RESULTS-2026-11-17.md). |
| Reviewed candidate source | PASS | WP14A `307e326`, WP14B `f5d69a9`, candidate `d125910`, and observer correction `8f0bbe1` are committed. Final validation records accompany this document in a separate evidence commit. |
| Final tag and publication | NOT AUTHORIZED | Current work covers candidate preparation and CI. Final tagging and publication require separate explicit user authorization. |

The scoped candidate checks above are complete. The final evidence commit's CI
is checked before handoff. Live observations constrain the workflow claims that
can be made; incomplete runtime evidence must not be converted to product
success or task failure.

## Installed-Skill evidence and limits

The [initial live sample](evaluations/INSTALLED-SKILL-LIVE-RESULTS-2026-11-16.md)
used real Codex with explicitly invoked, project-local installed Skill and CLI
files. `scoped-implementation` completed with PASS, including observable Skill
content, a complete strict read before modification, and artifact checks.
`missing-scope` and `unconfirmed-observation` each had runtime exit 1 and no
successful turn completion, so both remain infrastructure BLOCKER outcomes.

Their raw errors were not retained. Hashes and typed metadata do not establish
the original failure causes. Exact snapshots of the three mutable initial
method files are retained in the original record directory's
[method snapshot](evaluations/installed-skill-live-2026-11-16/method-snapshot/SNAPSHOT.json);
the unchanged fourth helper is pinned by its original hash.

The [2026-11-17 diagnostic plan](evaluations/INSTALLED-SKILL-LIVE-DIAGNOSTIC-PLAN-2026-11-17.md)
defined a new two-task sample with bounded diagnostic observations. Both sessions
completed: [missing-scope passed and unconfirmed-observation failed](evaluations/INSTALLED-SKILL-LIVE-DIAGNOSTIC-RESULTS-2026-11-17.md).
The latter passed its artifact checks but failed the recorded read-before-write
ordering check. Its early command's raw payload was not retained; at collection,
its identity and the cause of that particular failure were unknown.

An independently reproducible observer defect can classify single read-only
CLI help and preview calls as writes. The separately fixed
[observer-correction plan](evaluations/INSTALLED-SKILL-LIVE-OBSERVER-PLAN-2026-11-17.md)
required controls before one new independent candidate-task sample. It preserves
confirmed write-before-read failures and assigns uncertain ordering to REVIEW.
Neither the correction nor a later result regrades the earlier FAIL or replaces
its blockers, and the separate samples must not be pooled as an original 3/3
score or automatic-discovery evidence.

The [new independent sample](evaluations/INSTALLED-SKILL-LIVE-OBSERVER-RESULTS-2026-11-17.md)
passed: installed Skill content was observed at sequence 6, the complete strict
maintenance read at 11 preceded confirmed candidate writing at 14, and all
artifact checks passed. A separate read-only help event at 12 remained in the
legacy possible-event list while its verified classification was retained.

That new help event's command SHA-256 (`a7a1fdd5…77c483bb`) and output SHA-256
(`26c1c212…6c2d4b7d`), with exit 0, exactly match the old diagnostic event at
9–10. Given reliable hashes and no collision, this cross-sample association
supports the inference that the old early event was the same help call and its
ordering failure may reflect the observer defect. It is not a complete causal
reconstruction: the new help followed its strict read, whereas the old event
preceded it. No old result is regraded, and no discarded workspace is attested.

## Claims and deferred work

- The release can describe the versioned contracts, observed offline checks,
  and individually completed installed-workflow observations within their scope.
  An oracle defect alone does not prove a historical agent answer was correct
  or establish a production CLI defect.
- General effectiveness, token savings, cross-runtime conformance, automatic
  discovery, and production-repository reliability remain unsupported by these
  development samples. Source hashes support consistency, not tamper-proof
  runtime attestation or independent regrading of discarded workspaces.
- Production checkpointing remains deferred. The original interruption screen
  found no observable-summary advantage; it did not isolate a material
  interruption-specific failure or prove checkpointing generally useless.
  That deferral does not block the evaluation-reliability release scope.

The candidate is ready for review of this evaluation-reliability scope. Tagging,
merging, and publication are separate actions; this record does not announce a
published release or extend the measured workflow claims.
