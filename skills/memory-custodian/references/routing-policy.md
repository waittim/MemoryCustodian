# Deterministic Routing Policy

The manifest routes a bounded context pack from explicit task and scope inputs. It does not prove semantic relevance.

## Inputs

- Canonical tasks: `general`, `planning`, `implementation`, `artifact`, `preferences`, `history`, `maintenance`.
- Touched or planned repo-relative paths supplied with repeatable `--path`.
- Explicit enabled modules supplied with `--rule`, `--profile`, or `--area`.

Protocol 0.7 uses case-sensitive POSIX globs. `*` and `?` stay within one segment; `**` spans complete segments.
Paths are lexically contained in the project, checked against symlink escape, and need not exist yet. The CLI never
reads touched-file content to infer an area.

## Completeness

`COMPLETE` means the enabled routing dimensions received enough explicit input. `INCOMPLETE` means scope may change
the pack—for example, a substantial task has enabled path-routed areas but no paths or explicit areas. `AMBIGUOUS`
means a valid declared exclusivity cannot be resolved. `INVALID` means manifest grammar, metadata, or input violates
the protocol.

Default Protocol 0.7 manifests do not declare mutually exclusive routes. A customized manifest may assign the same
`exclusive-group` token to two or more path-activated areas. Resolve the group across every activation source:
exactly one explicit member selects it and suppresses other path activations; multiple explicit members, or multiple
path members without an explicit selection, emit `MC-ROUTE-AMBIGUOUS`. Load at most one group member and retain the
safe baseline on ambiguity. `exclusive-group` is invalid on rules, profiles, or explicit-only areas and is never
inferred.

Use `--strict-routing` before substantial planning, implementation, debugging, or review. An incomplete inspection
may show the shared safety baseline, but it is not an approved context pack.

## Explain

`read --explain` gives every enabled module exactly one file disposition: `loaded`, `skipped`,
`missing-required`, `missing-optional`, or `invalid`. Budget omissions are separate entry dispositions and use a real
Entry ID or stable file/unit reference. Stable `MC-ROUTE-*`, `MC-SKIP-*`, `MC-MISSING-*`, and `MC-OMIT-BUDGET`
codes state observable causes; skipped never means “not relevant.”

Root `constraints.md` is the generated safety baseline for substantial tasks. Custom Protocol 0.6 routes are
preserved during migration; missing root-constraint coverage remains a routing safety warning until reviewed.
