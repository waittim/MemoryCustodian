# route-notes-token-estimate v2 contract validation

Generated: 2026-11-17T04:19:46.794320+00:00
Task: `route-notes-token-estimate`, revision `2`.

Constructed offline cases only; no live-agent, effectiveness, or checkpoint claim.

| Case | Expected | v1 oracle | v2 oracle | Contract check |
| --- | --- | --- | --- | --- |
| reference | PASS | PASS | PASS | PASS |
| unicode-regex | PASS | PASS | PASS | PASS |
| manual-state-machine | PASS | PASS | PASS | PASS |
| word-start-generator | PASS | PASS | PASS | PASS |
| splitlines-word-sum | PASS | PASS | PASS | PASS |
| constant-three | FAIL | PASS | FAIL | PASS |
| line-counter | FAIL | FAIL | FAIL | PASS |
| character-counter | FAIL | FAIL | FAIL | PASS |
| literal-space-split | FAIL | FAIL | FAIL | PASS |
| line-count-mixture | FAIL | FAIL | FAIL | PASS |
| sample-only | FAIL | PASS | FAIL | PASS |
| boolean-zero | FAIL | PASS | FAIL | PASS |
| floating-count | FAIL | PASS | FAIL | PASS |
| negative-count | FAIL | FAIL | FAIL | PASS |
| stale-first-result | FAIL | PASS | FAIL | PASS |
| unstable-repeat | FAIL | PASS | FAIL | PASS |
| string-only | FAIL | PASS | FAIL | PASS |
| ascii-regex | FAIL | PASS | FAIL | PASS |
| bounded-count | FAIL | PASS | FAIL | PASS |

Contract checks passed: 19/19.
The v1 oracle rejected 0 positive examples and accepted 9 negative examples in this constructed set.

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
  --task route-notes-token-estimate --task-version 2
```

## Revision-specific interpretation

The [public v2 contract](../../../benchmarks/task-revisions/route-notes-token-estimate/v2/public-contract.md)
defines `len(str(text).split())` semantics, Unicode whitespace, integer results,
and stable repeated calls. A constant `3` reproduces the old single-input
oracle's acceptance gap. Some controls also enforce newly explicit v2 type and
string-conversion requirements; their classes do not retrospectively change the
v1 public contract or any historical agent result. Finite behavioral checks are
not a general model tokenizer or an anti-cheating proof.
