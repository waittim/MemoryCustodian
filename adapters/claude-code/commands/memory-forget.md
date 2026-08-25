# memory-forget

Run:

```bash
memory-custodian forget "<topic>" --mode soft
# Review the preview, then apply its Plan ID:
memory-custodian forget "<topic>" --mode soft --apply --confirm-plan <PLAN_ID>
```

Use `--mode hard` or `--mode purge` only when explicitly requested. Hard upgrades prior topic-bearing soft tombstones to a generic guard; purge removes them. If preview reports `Manual rewrite required`, rewrite the body or preamble semantically before applying.

Report the boundary exactly as shown by the preview: hard removes matching active managed memory, while purge also
targets managed `archive/`. Neither mode rewrites Git history, commits the working tree, or revokes clones, forks,
backups, caches, and other distributed copies. Never describe either result as permanent deletion everywhere.
