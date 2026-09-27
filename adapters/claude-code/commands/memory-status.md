# memory-status

Run:

```bash
memory-custodian status
memory-custodian check
memory-custodian check --privacy
memory-custodian check --security
```

For automation, also use:

```bash
memory-custodian audit --format json
memory-custodian audit --transactions
```

Report missing files, over-budget files, inbox size, optional module state,
protocol consistency, and transaction recovery state. Do not load archive
content for this command. A transaction finding requires explicit opaque-ID
recovery; it is not silently discarded.
