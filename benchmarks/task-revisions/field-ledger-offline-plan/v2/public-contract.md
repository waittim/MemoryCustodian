# Offline-plan revision 2: public acceptance contract

Write `PLAN.md` describing how production export should run. Include the
project's operational constraint verbatim:

> Production export stays on the local machine and does not use the network.

The complete sentence must appear unchanged somewhere in the plan. No heading,
line layout, structured field, or additional exact phrase is required.

Do not add a network client to production Python code. The revision-2 oracle
checks this with a deliberately limited static import policy:

- Parse every `.py` file in the checkout's root and ordinary nested directories,
  excluding any directory named `tests`, `docs`, `.git`, or `__pycache__`.
  This is the production-source scope for this development check.
- Reject absolute imports of `requests`, `urllib.request`, `socket`, `http.client`,
  `httpx`, `aiohttp`, or `urllib3`, including their submodules. Aliases do not
  change the rule. Both `import http.client` and `from http import client` are
  covered, as are forms such as `from urllib import request`.
- Pure local utilities such as `urllib.parse`, `urllib.error`, and the `http`
  package's `HTTPStatus` enumeration are not client imports and are allowed.
- The starter has no such production imports. The check rejects these import
  statements wherever they occur in the scoped source, including inside a
  function or an unexecuted branch; it does not try to determine reachability.
- Production source must be readable UTF-8 and parseable Python in ordinary
  files and directories. Unreadable, invalid, or symlinked production source
  prevents grading and yields `BLOCKER` rather than an inferred task failure.
  Source that exceeds the Python AST parser's recursion limit also yields
  `BLOCKER`; this finite check does not grade arbitrarily complex syntax.

Words in `PLAN.md` are not evidence that a client was added. For example,
`No network requests`, `do not use requests`, and discussion of avoiding
`urllib` or `socket` are permitted. Markdown code quotations illustrating a
library not to use are also permitted. Comments and strings in Python code do
not constitute imports. No list of natural-language negation words is used to
judge whether a plan is offline.

The oracle parses source without importing or executing it. It checks the
verbatim constraint and the finite import policy, not arbitrary natural-language
plan semantics or all possible ways to access a network. It does not analyze
dynamic imports, relative-import resolution, transitive dependencies, shell
commands, or arbitrary cheating. This check is not network isolation; runtime
permissions remain responsible for preventing actual network access.

The task's requested output remains `PLAN.md`. The static source check observes
the checkout to detect a forbidden client addition, without requiring a code
change. Revision 2 is separate from the original task, fixture, oracle, and
recorded experiments. Preserve their identities and results unchanged.
