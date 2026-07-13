# memory-compact

Run a dry run first:

```bash
memory-custodian compact
```

If the proposed deterministic changes are appropriate, run:

```bash
memory-custodian compact --apply
```

For an over-budget active file, run a target dry run:

```bash
memory-custodian compact --target decisions.md
```

First shorten decisions over 120 tokens, merge superseded entries, move subsystem knowledge into matched areas, and retain active invariants in normal loading paths. Then apply only after reviewing the plan:

```bash
memory-custodian compact --target decisions.md --apply --archive-oldest
```

For semantic compaction, read `skills/memory-custodian/references/compaction-policy.md` and update memory files directly.
