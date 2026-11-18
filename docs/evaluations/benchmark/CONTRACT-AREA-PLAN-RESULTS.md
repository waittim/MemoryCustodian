# route-notes-no-prose-area v2 contract validation

Generated: 2026-11-17T03:18:31.889582+00:00
Task: `route-notes-no-prose-area`, revision `2`.

Constructed offline cases only; no live-agent, effectiveness, or checkpoint claim.

| Case | Expected | v1 oracle | v2 oracle | Contract check |
| --- | --- | --- | --- | --- |
| reference | PASS | PASS | PASS | PASS |
| negative-load-explanation | PASS | FAIL | PASS | PASS |
| paragraph-rules | PASS | PASS | PASS | PASS |
| surrounding-whitespace | PASS | PASS | PASS | PASS |
| backtick-fenced-action | PASS | PASS | PASS | PASS |
| tilde-fenced-action | PASS | PASS | PASS | PASS |
| quoted-load-explanation | PASS | FAIL | PASS | PASS |
| inline-code-load-explanation | PASS | FAIL | PASS | PASS |
| quoted-string-load-explanation | PASS | FAIL | PASS | PASS |
| repeated-skip | PASS | PASS | PASS | PASS |
| missing-first-rule | FAIL | FAIL | FAIL | PASS |
| missing-second-rule | FAIL | FAIL | FAIL | PASS |
| inline-skip | FAIL | PASS | FAIL | PASS |
| load-action | FAIL | FAIL | FAIL | PASS |
| conflicting-actions | FAIL | FAIL | FAIL | PASS |
| fenced-load-conflict | FAIL | FAIL | FAIL | PASS |
| misspelled-path | FAIL | FAIL | FAIL | PASS |
| explanation-without-action | FAIL | FAIL | FAIL | PASS |
| capitalized-action | FAIL | FAIL | FAIL | PASS |
| inline-code-skip-only | FAIL | PASS | FAIL | PASS |
| list-item-skip-only | FAIL | PASS | FAIL | PASS |
| quoted-skip-only | FAIL | PASS | FAIL | PASS |
| skip-with-inline-comment | FAIL | PASS | FAIL | PASS |

Contract checks passed: 23/23.
The v1 oracle rejected 4 positive examples and accepted 5 negative examples in this constructed set.

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
  --task route-notes-no-prose-area --task-version 2
```

## Revision-specific interpretation

The [v2 public contract](../../../benchmarks/task-revisions/route-notes-no-prose-area/v2/public-contract.md)
defines a narrow standalone action-line protocol and discloses its treatment of
whitespace, fences, quotes, and explanatory prose. These controls follow that
explicit v2 syntax; they do not retrospectively score an agent's intent or prove
which files an agent read. The negative-load explanation and inline-only skip
controls reproduce the original false rejection and missing own-line check.
