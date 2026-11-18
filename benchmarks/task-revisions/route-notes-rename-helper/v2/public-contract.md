# Rename-selection-helper revision 2: public acceptance contract

Move the starter's selection behavior into the public function
`select_for_task(task, manifest, available)`. Keep
`select_files(task, manifest, available)` as the public delegation wrapper.
The function names are required by this task; their source-code spelling,
formatting, temporary variable names, and choice of sorting expression are not
acceptance criteria.

Preserve the starter's observable selection behavior:

- The result is a list containing every element of `available`, in Python's
  ordinary ascending sorted order. Keep duplicate values and complete path
  strings, including any `archive/` paths present in the supplied input.
- Accept sortable path strings supplied as a list, tuple, or finite one-pass
  iterable. Preserve a supplied list or tuple rather than sorting it in place.
  A one-pass iterable is consumed to produce the result, as with `sorted()`.
- Return a new result list on each call. Do not return a shared cached answer.
- As in the starter's `sorted(available)` implementation, `task` and `manifest`
  do not affect the result and are not mutated. Arbitrary task values and
  manifests are valid, including an unknown task or a manifest without a
  matching task entry. This refactoring task preserves existing behavior;
  introducing manifest filtering, archive filtering, or deduplication changes
  that behavior.

The v2 delegation check makes the wrapper's dependency explicit: on each call,
`select_files` calls the currently bound `router.select_for_task` exactly once,
forwards the same `task`, `manifest`, and `available` objects, and returns that
helper's result object unchanged. Positional calls, named arguments, and an
alias resolved inside the wrapper call are valid. An alias permanently captured
when the module was imported, a wrapper that recomputes selection itself, a
wrapper that ignores the helper's result, and a wrapper that consumes or copies
the input before forwarding it do not meet this v2 delegation contract.

For example, both `sorted(list(available))` and sorting a newly created local
list with `.sort()` are valid helper implementations. No literal occurrence
of `sorted(available)` is required.

The development oracle checks finite behavioral samples and temporarily
replaces the public helper with a recording sentinel to test delegation. It
does not search source text or require an AST shape. These checks are not a
security boundary or a proof against arbitrary cheating, and they do not prove
the correctness of every possible iterable or custom comparison operator.
Tests use homogeneous path strings and finite iterables.

Revision 2 is independent of the original version-1 task, fixture, reference,
oracle, and experiments. Keep results identified by their oracle revision;
do not overwrite or reinterpret version-1 results using this contract.
