# Split-export v2 contract validation

Generated: 2026-11-16T22:08:26.213645+00:00
Task: `field-ledger-split-export`, revision `2`.

Constructed offline cases only; no live-agent, effectiveness, or checkpoint claim.

| Case | Expected | v1 oracle | v2 oracle | Contract check |
| --- | --- | --- | --- | --- |
| reference | PASS | PASS | PASS | PASS |
| renamed-helper | PASS | FAIL | PASS | PASS |
| module-alias | PASS | FAIL | PASS | PASS |
| local-import | PASS | FAIL | PASS | PASS |
| empty-module | FAIL | FAIL | FAIL | PASS |
| comment-masquerade | FAIL | PASS | FAIL | PASS |
| unused-helper | FAIL | PASS | FAIL | PASS |
| dead-branch-helper | FAIL | PASS | FAIL | PASS |
| ignored-helper | FAIL | FAIL | FAIL | PASS |
| reexport-unmoved | FAIL | PASS | FAIL | PASS |
| drop-row | FAIL | FAIL | FAIL | PASS |
| reverse-rows | FAIL | PASS | FAIL | PASS |
| fixed-cap | FAIL | PASS | FAIL | PASS |
| alias-list | FAIL | PASS | FAIL | PASS |
| deep-copy-rows | FAIL | PASS | FAIL | PASS |

Contract checks passed: 15/15.
The v1 oracle rejected 3 positive examples and accepted 8 negative examples in this constructed set.

## Scope and interpretation

The v2 public contract explicitly locates row selection and construction of the returned list in export.py.
Helper names and import spelling are unrestricted. Behavior checks cover row content/order, dynamic caps, and shallow-list semantics.
Runtime call/return evidence checks delegation without matching source strings; this is not an adversarial anti-cheating guarantee.
This development revision is informed by the pilot outcomes and cannot be treated as held-out evidence.
The old task, fixture, reference, v1 oracle, frozen runtime methods, and historical result records remain unchanged.
These are newly constructed examples, not regrading of discarded agent workspaces; historical scores are not revised.
Oracle weaknesses alone do not establish that an actual historical agent output was correct or that production Skill/CLI behavior is defective.

## Provenance and reproduction

Each record pins the base task, fixture, v1 oracle/reference, v2 descriptor/oracle/public contract/cases, and method sources.
The two graders receive separate checkouts with identical input hashes. Infrastructure failures stay BLOCKER.
Records use exclusive creation and a directory separate from the historical pilots.

```bash
python3 scripts/check-benchmark-contracts.py \
  --task field-ledger-split-export --task-version 2
```
