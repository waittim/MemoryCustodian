# Local Overlay Policy

Protocol 0.8 MAY store user/machine preferences outside the repository at
`<state-root>/projects/<project_id>/local/`. Directories are private (`0700` on POSIX), files are private (`0600`),
and state helpers reject symlink replacement.

An existing overlay loads only when its shared `project_id` matches and the normalized repository root appears in
the repo-external `bindings.json`. A copied repository with the same public project ID is `UNBOUND`; use
`memory-custodian local link` explicitly. Multiple bound roots are `REVIEW`, not silent sharing.

Precedence is fixed:

1. System, current user, safety, and permissions
2. Shared constraints and tombstones
3. Shared decisions and rules
4. Local preferences and profiles
5. Task convenience

Local modules use only active Entries with `Scope: local-user` or `Scope: local-machine`. They cannot redefine shared
routes, create `Exception-To`, supersession, promotion, or other governance relations, grant authority, or store
secrets. Entry IDs MUST remain unique across shared and local storage. `read --no-local` produces shared-only context.

`local status`, `enable`, `link`, and `add` use the Protocol 0.8 contract.
`local reset` previews and applies through the shared transaction journal and
uses the same canonical ErasureScope as forgetting. Its file deletions and
empty-directory cleanup are recoverable together; a recovered completion
reports the overlay removed only after the journaled directories are gone.
It never claims to affect other machines, backups, or distributed copies.
