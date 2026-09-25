# Protocol 0.8 Transaction and Recovery Policy

MemoryCustodian 0.12 uses transaction schema 1 for every mutation that can
change more than one managed target. The transaction engine is shared by
`init`/repair, enable/link, add and promotion, compact, forget/hard-forget/
purge, Subject and reconciliation governance, staged migration, schema
conversion, and local reset. A command that only previews a plan does not
write managed files; an apply must use the matching `--confirm-plan` and the
same lock-held rebuild/validation.

## Private journal

The journal lives in the repo-external MemoryCustodian state root, never in
`docs/memory/` or a context pack. It is private state (`0700` directories and
`0600` regular files on POSIX). Journal metadata contains only a generic
operation, opaque transaction/target identifiers, digests, modes, and
redacted root-qualified locators. It must not contain a user topic, removed
body, secret preview, or a reversible encoding of one. Protected rollback
bytes may contain the pre-operation content because recovery needs them; they
are never reader/audit/public output and are removed after safe completion.

The journal is persisted in `planned` before any backup or prepared output is
created, then moves through `prepared`, `committing`, `failed`, or
`recovering`. Journal updates are atomic. Create, replace, and delete targets
record existence, raw-byte digest, and mode so recovery can distinguish a
valid base from a committed output.

## Crash recovery

`audit --transactions` must report unfinished, malformed, unsupported, or
orphaned private transaction state; it must not silently delete it. Use the
opaque transaction ID with:

```bash
memory-custodian recover --transaction-id <OPAQUE_ID>
memory-custodian recover --transaction-id <OPAQUE_ID> --complete
memory-custodian recover --transaction-id <OPAQUE_ID> --rollback
```

Recovery takes the same permanent/bootstrap lock and blocks new mutations.
Complete is allowed only when every target still matches the recorded base or
prepared output and the prepared digest is valid. Rollback restores the
protected pre-state only when the target has not been externally changed.
Symlink replacement, mode changes, missing state, malformed journals, or
unexpected digests require review/manual recovery; recovery never overwrites
an external edit. After complete or rollback, prepared files and backups are
cleaned according to the private-state policy.

Recovery output uses the same public output envelope and canonical
`ErasureScope` used by forgetting. `recovered-complete` means the prepared
managed result was committed; `recovered-rollback` means the protected
pre-state was restored. These statuses describe managed state only.

This is a crash-recovery protocol, not a database ACID guarantee, semantic
conflict resolver, or proof of filesystem, Git-history, clone, fork, backup,
cache, or distributed-copy erasure.
