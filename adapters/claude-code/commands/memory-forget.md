# memory-forget

Run:

```bash
memory-custodian forget "<topic>" --mode soft
# Review the preview, then apply:
memory-custodian forget "<topic>" --mode soft --apply
```

Use `--mode hard` or `--mode purge` only when explicitly requested. Hard upgrades prior topic-bearing soft tombstones to a generic guard; purge removes them. If preview reports `Manual rewrite required`, rewrite the body or preamble semantically before applying.
