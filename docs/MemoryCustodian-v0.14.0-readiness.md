# MemoryCustodian v0.14.0 candidate readiness

Updated: 2026-11-17. Status: candidate preparation; release gates remain open.

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
| Full local unittest suite | PASS | 602 tests passed on 2026-11-17. The prior static package-version expectation was synchronized, and eval version fields now participate in the version-drift gate. |
| Initial installed-Skill live sample | PARTIAL | 2026-11-16: one PASS, two infrastructure BLOCKER outcomes; see the separate evidence below. |
| Diagnostic follow-up | PENDING | The separately fixed 2026-11-17 sample covers only the two tasks without completed initial results. Record its outcomes independently. |
| Remote compatibility CI | PENDING | Linux/Windows and Python 3.10–3.14 checks have not run for the final candidate. Link the successful candidate-commit runs here when available. |
| Reproducible distribution builds | PENDING | Build ZIP and tar.gz twice from the same candidate source; compare hashes and inspect archive contents. |
| Reviewed candidate commit | PENDING | WP14A `307e326` and WP14B `f5d69a9` are committed; the remaining candidate changes still need a reviewed commit. |
| Final tag and publication | NOT AUTHORIZED | Current work covers candidate preparation and CI. Final tagging and publication require separate explicit user authorization. |

Local checks, candidate CI, reproducible builds, and the reviewed commit are
required before marking this candidate release-ready. Live observations constrain
the workflow claims that can be made; incomplete runtime evidence must not be
converted to product success or task failure.

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
defines a new two-task sample with bounded diagnostic observations. Results are
pending. Even if both complete, they must not be combined with the initial PASS
to present the original cohort as 3/3, replace its blockers, or imply automatic
Skill discovery.

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

Before final review, replace pending rows with actual results and CI links,
or explicitly narrow the release claims where evidence remains unavailable.
Do not mark unrun checks PASS.
