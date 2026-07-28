# memory-forget

Run:

```bash
memory-custodian forget "<topic>" --mode soft
# Review the preview, then apply its Plan ID:
memory-custodian forget "<topic>" --mode soft --apply --confirm-plan <PLAN_ID>
```

Use `--mode hard` or `--mode purge` only when explicitly requested. Hard upgrades prior topic-bearing soft tombstones to a generic guard; purge removes them. If preview reports `Manual rewrite required`, rewrite the body or preamble semantically before applying.
