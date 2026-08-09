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
is reserved for a future versioned exclusivity policy or documented compatibility mapping. Routing schema 1 defines
neither; `exclusive-group` is an unknown key and therefore `INVALID`. `INVALID` means manifest grammar, metadata, or
input violates the protocol.

Use `--strict-routing` before substantial planning, implementation, debugging, or review. An incomplete inspection
may show the shared safety baseline, but it is not an approved context pack.

## Explain

`read --explain` gives every enabled module exactly one file disposition: `loaded`, `skipped`,
`missing-required`, `missing-optional`, or `invalid`. Budget omissions are separate entry dispositions and use a real
Entry ID or stable file/unit reference. Stable `MC-ROUTE-*`, `MC-SKIP-*`, `MC-MISSING-*`, and `MC-OMIT-BUDGET`
codes state observable causes; skipped never means “not relevant.”

Root `constraints.md` is the generated safety baseline for substantial tasks. Custom Protocol 0.6 routes are
preserved during migration; missing root-constraint coverage remains a routing safety warning until reviewed.
