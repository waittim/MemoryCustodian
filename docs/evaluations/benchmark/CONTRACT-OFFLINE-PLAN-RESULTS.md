# field-ledger-offline-plan v2 contract validation

Generated: 2026-11-17T04:19:46.090904+00:00
Task: `field-ledger-offline-plan`, revision `2`.

Constructed offline cases only; no live-agent, effectiveness, or checkpoint claim.

| Case | Expected | v1 oracle | v2 oracle | Contract check |
| --- | --- | --- | --- | --- |
| reference | PASS | PASS | PASS | PASS |
| no-network-requests | PASS | FAIL | PASS | PASS |
| avoid-network-libraries | PASS | FAIL | PASS | PASS |
| code-quotation | PASS | FAIL | PASS | PASS |
| inline-code-discussion | PASS | FAIL | PASS | PASS |
| paragraph-constraint | PASS | PASS | PASS | PASS |
| quoted-constraint | PASS | PASS | PASS | PASS |
| request-terminology | PASS | FAIL | PASS | PASS |
| empty-plan | FAIL | FAIL | FAIL | PASS |
| missing-constraint | FAIL | FAIL | FAIL | PASS |
| changed-constraint | FAIL | FAIL | FAIL | PASS |
| truncated-constraint | FAIL | FAIL | FAIL | PASS |
| capitalized-constraint | FAIL | FAIL | FAIL | PASS |

Contract checks passed: 13/13.
The v1 oracle rejected 5 positive examples and accepted 0 negative examples in this constructed set.

## Scope and interpretation

The task revision's public-contract.md is visible as TASK-CONTRACT.md in every constructed checkout.
Acceptance follows that explicit task contract, with positive and negative controls for behavior and supported syntax.
These finite development checks are not an adversarial anti-cheating guarantee or a general natural-language evaluator.
This development revision is informed by the pilot outcomes and cannot be treated as held-out evidence.
The old task, fixture, reference, v1 oracle, frozen runtime methods, and historical result records remain unchanged.
These are newly constructed examples, not regrading of discarded agent workspaces; historical scores are not revised.
Oracle weaknesses alone do not establish that an actual historical agent output was correct or that production Skill/CLI behavior is defective.

## Provenance and reproduction

Each record pins the base task, fixture, v1 oracle/reference, v2 descriptor/oracle/public contract/cases, and method sources.
The two graders receive separate checkouts with identical input hashes. Infrastructure failures stay BLOCKER.
Records use exclusive creation and a directory separate from the historical pilots.

Each record retains method source hashes and Git context. A later validator implementation may differ; historical records are not overwritten.

```bash
python3 scripts/check-benchmark-contracts.py \
  --task field-ledger-offline-plan --task-version 2
```

## Revision-specific interpretation

The [public v2 contract](../../../benchmarks/task-revisions/field-ledger-offline-plan/v2/public-contract.md)
requires the original operational sentence and a finite static import policy;
it does not classify arbitrary natural-language intent. These 13 constructed
records vary the requested `PLAN.md` output. Separate regression tests inject
actual production Python files to verify rejection of client imports, acceptance
of local URL utilities, no source execution, and `BLOCKER` for unavailable or
unparseable source, including parser-complexity limits where applicable.

Mentioning a forbidden library in explanatory prose is not evidence that an
agent added a client. The original agent outputs are not regraded.
