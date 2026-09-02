# Manifest Policy

`manifest.md` is the sole shared runtime routing authority. Protocol 0.7 declares entry, Subject, routing, and
conflict schema version 1; a persistent UUIDv4 `project_id`; `subject_registry: subjects.md`;
`admission_policy: evidence-required`; `routing_policy: explicit-task-and-scope`; and
`conflict_policy: canonical-subject-and-review`. The public project ID is a namespace identifier, not a secret or
authorization token.

The generated manifest always loads `brief.md` and `constraints.md`. Root constraints are the safety baseline for
substantial planning, implementation, artifact, and history work. Custom migrated routes remain authoritative;
`check --routing` warns when a substantial route does not reach root constraints.

## Task Routes

Choose one canonical task: `general`, `planning`, `implementation`, `artifact`, `preferences`, `history`, or
`maintenance`. Aliases normalize deterministically. Never classify arbitrary task prose inside the CLI or
supplement a valid custom manifest from an adapter, template, or remembered default.

Normal loading combines always-load files, the canonical task route, and Protocol 0.7 optional declarations.
Candidates do not enter normal context. `inbox.md` is maintenance/candidate-review only; `archive/` is explicit or
archive-maintenance only.

## Optional Module Grammar

Each enabled module has one canonical repo-relative path and one declaration:

```markdown
### Enabled rules
- `rules/output.md`
  - activation: task-or-explicit
  - tasks: artifact
  - description: Public output rules.

### Enabled profiles
- `profiles/git.md`
  - activation: explicit-only

### Enabled areas
- `areas/backend.md`
  - activation: path-or-explicit
  - paths: `cli/**`, `tests/**/*.py`
```

Allowed metadata keys are `activation`, `tasks`, `paths`, and `description`. Duplicate modules or scalar keys,
unknown keys, malformed indentation, unsafe paths, invalid globs, and incompatible module metadata are INVALID.
Rules use `task`, `task-or-explicit`, or `explicit-only`; profiles are `explicit-only`; areas use `path`,
`path-or-explicit`, or `explicit-only`. Descriptions are preserved but never affect routing identity or Plan IDs.

Protocol 0.6 one-line natural-language triggers migrate conservatively to `explicit-only`; the description is
preserved and the CLI reports that manual automatic-route mapping is required. Migration never guesses task or
path matchers.

## Conflict and Trust Boundaries

Memory cannot override system/current-user instructions, safety, or permissions, and cannot authorize destructive
actions, secret access, external uploads, commits, pushes, merges, releases, or escalation. Shared constraints and
tombstones outrank local overlay preferences. Area exceptions require a valid `Exception-To` relationship rather
than an implicit override.

See `routing-policy.md` for path matching, completeness, explain, and strict mode; see
`local-overlay-policy.md` for repo-external local precedence and binding.
