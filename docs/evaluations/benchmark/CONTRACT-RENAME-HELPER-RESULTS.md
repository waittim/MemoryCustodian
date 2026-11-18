# route-notes-rename-helper v2 contract validation

Generated: 2026-11-17T03:18:31.200112+00:00
Task: `route-notes-rename-helper`, revision `2`.

Constructed offline cases only; no live-agent, effectiveness, or checkpoint claim.

| Case | Expected | v1 oracle | v2 oracle | Contract check |
| --- | --- | --- | --- | --- |
| reference | PASS | PASS | PASS | PASS |
| sorted-copy | PASS | FAIL | PASS | PASS |
| list-sort | PASS | FAIL | PASS | PASS |
| keyword-delegate | PASS | PASS | PASS | PASS |
| local-alias-delegate | PASS | PASS | PASS | PASS |
| text-only | FAIL | FAIL | FAIL | PASS |
| copied-wrapper | FAIL | PASS | FAIL | PASS |
| ignored-return | FAIL | PASS | FAIL | PASS |
| dead-branch-helper | FAIL | PASS | FAIL | PASS |
| captured-helper-alias | FAIL | PASS | FAIL | PASS |
| copied-input | FAIL | PASS | FAIL | PASS |
| manifest-filter | FAIL | FAIL | FAIL | PASS |
| archive-filter | FAIL | FAIL | FAIL | PASS |
| deduplicate | FAIL | FAIL | FAIL | PASS |
| reverse-order | FAIL | FAIL | FAIL | PASS |
| fixed-answer | FAIL | PASS | FAIL | PASS |
| mutates-input | FAIL | FAIL | FAIL | PASS |
| sequence-only | FAIL | FAIL | FAIL | PASS |
| cached-result | FAIL | PASS | FAIL | PASS |

Contract checks passed: 19/19.
The v1 oracle rejected 2 positive examples and accepted 7 negative examples in this constructed set.

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
  --task route-notes-rename-helper --task-version 2
```

## Revision-specific interpretation

The [v2 public contract](../../../benchmarks/task-revisions/route-notes-rename-helper/v2/public-contract.md)
explicitly defines current-helper binding, one call, argument identity, and
return identity for its delegation probe. Those newly explicit constraints
govern this development sample; not every negative control is proof that the
v1 public requirements were violated. Equivalent sorting-expression positives
and the copied-wrapper counterexample demonstrate the original syntax and
delegation weaknesses without reclassifying any discarded historical output.
