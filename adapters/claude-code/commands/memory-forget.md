# memory-forget

Run:

```bash
memory-custodian forget "<topic>" --mode soft
# Review the preview, then apply:
memory-custodian forget "<topic>" --mode soft --apply
```

Use `--mode hard` or `--mode purge` only when explicitly requested. Respect tombstones after forgetting.
