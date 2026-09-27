# Protocol 0.8 Transaction and Recovery Policy

MemoryCustodian 0.12 uses transaction schema 1 for every mutation that can
change more than one managed target. The transaction engine is shared by
`init`/repair, enable/link, add and promotion, compact, forget/hard-forget/
purge, Subject and reconciliation governance, staged migration, schema
conversion, and local reset. A command that only previews a plan does not
write managed files; an apply MUST use the matching `--confirm-plan` and the
same lock-held rebuild/validation.

## Private journal

The journal lives in the repo-external MemoryCustodian state root, never in
`docs/memory/` or a context pack. It is private state (`0700` directories and
`0600` regular files on POSIX). Journal metadata contains only a generic
operation, opaque transaction/target identifiers, digests, modes, and
redacted root-qualified locators. It MUST NOT contain a user topic, removed
body, secret preview, or a reversible encoding of one. Protected rollback
bytes MAY contain the pre-operation content because recovery needs them; they
are never reader/audit/public output and are removed after safe completion.

The journal is persisted in `planned` before any backup or prepared output is
created, then moves through `prepared`, `committing`, `failed`, or
`recovering` to `committed` or `rolled-back`. Journal updates are atomic.
Recovery records its chosen complete/rollback action before changing a target;
a retry MUST keep that action. A terminal journal remains recovery-visible
until cleanup finishes, including when only the journal itself remains.
Before deleting protected artifacts, cleanup MUST recheck that committed
targets still match their outputs, rolled-back targets still match their bases,
and committed created directories still exist. A mismatch requires review.
An empty private transaction directory left after journal unlink has no
recovery operands and is pruned under the next mutation lock. A directory
with content but no valid journal remains an orphan blocker.
Create, replace, and delete targets record existence, raw-byte digest, and
mode so recovery can distinguish a valid base from a committed output.
Local reset also journals the identity and mode of directories to remove.
It removes them only after the committed marker, deepest first and only when
empty. A new child or changed directory identity blocks automatic cleanup;
rollback leaves those original directories in place.
An older interrupted local-reset journal without that inventory requires
manual review while the overlay directory still exists; completion MUST NOT
claim the overlay was removed.

## Crash recovery

`audit --transactions` MUST report unfinished, malformed, unsupported, or
orphaned private transaction state; it MUST NOT silently delete it. Use the
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
an external edit. A committed journal can only finish completion, and a
rolled-back journal can only finish rollback cleanup. After complete or
rollback, prepared files and backups are cleaned according to the
private-state policy.

Recovery output uses the same public output envelope and canonical
`ErasureScope` used by forgetting. `recovered-complete` means the prepared
managed result was committed; `recovered-rollback` means the protected
pre-state was restored. These statuses describe managed state only.

This is a crash-recovery protocol, not a database ACID guarantee, semantic
conflict resolver, or proof of filesystem, Git-history, clone, fork, backup,
cache, or distributed-copy erasure.
