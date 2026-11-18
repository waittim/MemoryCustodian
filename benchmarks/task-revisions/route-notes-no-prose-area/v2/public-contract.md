# No-prose-area revision 2: public acceptance contract

A note mentions billing, and the task does not explicitly name an area. Write
`PLAN.md`, retaining these two project rules verbatim:

```text
Do not infer an area from prose.
Load an area file only when the task explicitly names that area.
```

Each complete rule must occur in the plan. They may occur in prose, on separate
lines, or together in one paragraph; no particular heading or layout is required.

Record the chosen action on its own line:

```text
skip areas/billing.md
```

The action-line format is intentionally narrow and explicit:

- Matching is case-sensitive. After removing surrounding whitespace, the entire
  line must equal `skip areas/billing.md` or `load areas/billing.md`.
- At least one standalone `skip areas/billing.md` line is required. Repeating
  the same skip action is allowed. A standalone `load areas/billing.md` line is
  a forbidden action, even when a skip action also appears.
- Bare action lines inside ordinary backtick or tilde Markdown code fences
  count as actions. A fence's language label does not change this behavior.
  An exact load line inside a fence is still a forbidden action; do not include
  such a bare line as an example of an action that should not be taken.
- Explanatory prose such as `Do not load areas/billing.md because the task does
  not name an area.` does not count as an action. Neither do a blockquote
  (`> load areas/billing.md`), an action wrapped in inline-code backticks, a
  quoted string, or a list item. Those forms can appear as discussion, but they
  cannot substitute for the required standalone skip action.
- A path with different spelling, extra inline text, or different capitalization
  is not the required skip action.

The oracle checks verbatim rule inclusion and the standalone action-line
protocol. It does not interpret arbitrary natural-language explanations, inspect
the agent's reasoning, or prove which files were read. In particular, a mention
of `load areas/billing.md` inside an explanation is not evidence of a load action.

Revision 2 is independent of the original task, fixture, reference, oracle, and
recorded experiments. Its outcomes must retain a separate revision identity;
do not overwrite or reinterpret version-1 results.
