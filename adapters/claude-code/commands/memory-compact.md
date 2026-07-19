# memory-compact

Run a dry run first:

```bash
memory-custodian compact
```

The report lists exact duplicate top-level bullet units, exact tombstone matches, and candidates requiring Agent review. Each top-level bullet unit includes its continuation and nested lines; nested bullets are never cleanup candidates on their own. For each candidate, determine scope, type, confidence, and whether equivalent memory already exists. Then edit the appropriate Markdown directly or use `memory-custodian add`.

If the exact mechanical cleanup is appropriate, run:

```bash
memory-custodian compact --apply
```

This command does not classify or promote candidates. It only removes the exact duplicate complete units and tombstone matches shown in the preview; reviewed candidates remain in the inbox until handled explicitly. Run `memory-custodian check` after semantic updates.

For an over-budget active file, run a target dry run:

```bash
memory-custodian compact --target decisions.md
```

First shorten decisions over 120 tokens, merge superseded entries, move subsystem knowledge into matched areas, and retain active invariants in normal loading paths. Then apply only after reviewing the plan:

```bash
memory-custodian compact --target decisions.md --apply --archive-oldest
```

For semantic compaction, read `skills/memory-custodian/references/compaction-policy.md` and update memory files directly.
