# Protocol 0.8 Output and Audit Contract

MemoryCustodian 0.12 uses Protocol 0.8, Entry schema 3, transaction schema 1,
audit schema 1, output schema 1, and ErasureScope schema 1. Subject,
conflict, routing, and local-overlay schema versions remain independently
declared by the manifest/state authority described in `manifest-policy.md`.

## Public envelope

`--format text` is the human renderer and `--format json` emits exactly one
UTF-8 JSON document on stdout. `--json` may remain a compatibility alias, but
documentation and fixtures use `--format json`. Fatal argument/runtime errors
are written to stderr; domain validation failures in JSON mode still return a
valid envelope:

```json
{
  "output_schema_version": 1,
  "command": "audit",
  "protocol_version": "0.8",
  "status": "REVIEW",
  "exit_class": "success-with-review",
  "data": {"audit_schema_version": 1},
  "findings": [],
  "disclaimers": []
}
```

Top-level `status` is only `PASS`, `REVIEW`, or `FAIL`. `exit_class` is one of
`success`, `success-with-review`, `domain-failure`, `blocker`, or `fatal`.
PASS/REVIEW return 0, ERROR/domain-failure returns 1, and BLOCKER/fatal
returns 2. A finding has a stable code, one of `INFO`, `WARNING`, `ERROR`, or
`BLOCKER`, a repository-relative POSIX path (or a stable private alias), an
optional Entry ID, message, and remediation. WARNINGS produce REVIEW; ERROR
or BLOCKER produces FAIL. Text and JSON render the same result model.

Project audit (`audit`) checks persistent project state; invocation audit
(`read --explain` or `audit --routing-input`) checks one context route; the
repository check scripts check this source tree. They must not become three
independent routing, conflict, or severity implementations. `audit --format
json` places `audit_schema_version: 1` in `data`, not in the shared manifest.

## Internal/public separation

Internal execution plans may carry selectors and protected digests required to
rebuild a mutation. They are never serialized directly as public JSON. A
public preview uses opaque operation references, stable repo-relative or
root-qualified aliases, and no hard/purge topic, removed body, or
selector-dependent fingerprint. The private transaction journal retains only
the protected metadata needed for stale-plan and recovery checks.

## Canonical ErasureScope

Forget, `forget --id`, hard/purge, local reset, and recovery all expose the
same versioned child object at `data.erasure_scope`:

```json
{
  "erasure_scope_schema_version": 1,
  "operation_phase": "preview",
  "active_memory": "pending-removal",
  "managed_archive": "not-targeted",
  "local_overlay": "not-applicable",
  "git_worktree_modified": "on-apply",
  "git_history_modified": false,
  "distributed_copies_revoked": false,
  "history_check_status": "not-requested",
  "topic_retained_in_new_records": true
}
```

`operation_phase` is `preview`, `applied`, `no-op`, `recovered-complete`, or
`recovered-rollback`. `active_memory`, `managed_archive`, and `local_overlay`
use `not-targeted`, `no-match`, `pending-removal`, `removed`, `restored`, or
`not-applicable`. `git_worktree_modified` uses `no`, `on-apply`, or `yes`.
`history_check_status` uses `not-requested`, `unavailable`,
`reachable-copy-detected`, or `no-reachable-copy-detected`.

`git_history_modified` and `distributed_copies_revoked` are false for normal
0.12 operations. `unavailable` is WARNING/REVIEW, not PASS. A bounded
`no-reachable-copy-detected` result is not evidence that dangling objects,
other refs, remotes, clones, forks, backups, caches, or exports do not exist.
The canonical boundary is:

> Forgetting controls what remains available to future agents through MemoryCustodian. It is not a guarantee of erasure from Git history or previously distributed copies.
