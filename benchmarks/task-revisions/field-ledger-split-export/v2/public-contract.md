# Split-export revision 2: public acceptance contract

Move export implementation into `export.py` and preserve the existing public
`Ledger.export()` behavior. `Ledger.export()` delegates to the list returned by
the implementation in `export.py`; that module owns row selection and creation
of the returned list. Helper names and import styles are unrestricted. For
example, a module alias, a renamed `from` import, or an import inside the method
are all valid. No particular helper name, including `export_entries`, is required.

Preserve these observable semantics from the starter:

- Export returns a list with the selected rows' complete contents and original
  order, including keys unrelated to the export implementation.
- The current value of `ledger.EXPORT_CAP` controls selection on every call:
  `None` returns every row; otherwise use ordinary Python `rows[:EXPORT_CAP]`
  semantics. This includes zero, negative limits, and limits beyond row count.
- Each call returns a new outer list, including for an empty ledger. The list
  is a shallow copy: its row dictionaries are the same objects as the selected
  dictionaries in `book.entries`. Returning `book.entries` itself or deep-copying
  rows changes the contract.
- Export does not mutate or replace `book.entries`, its row dictionaries, or
  `ledger.EXPORT_CAP`. Mutating the structure of the returned list does not
  mutate the ledger's list.
- The export remains local and uses no network or external service.

The development oracle checks behavior and actual execution, rather than
searching source text for an expected identifier. During a call to
`Ledger.export()`, it observes Python frames whose code belongs to the checkout's
`export.py` and requires that one such frame return the actual resulting list.
This accepts differently named helpers and ordinary import variations, and
rejects an empty module, an unused import, a comment mentioning a helper, a call
in an unexecuted branch, or an ignored no-op helper.

This profile-based observation is a development contract check, not a security
boundary or proof against arbitrary cheating. In particular, it does not prove
that no processing happened before a helper call. It does not enforce an AST
shape for the wrapper. The behavioral samples are finite, and the oracle is not
a network sandbox. Runtime permission controls remain responsible for network
and filesystem boundaries.

Revision 2 is separate from the original version-1 task, fixture, reference,
oracle, and recorded experiments. Results under the two oracle revisions must
retain their own identities and must not overwrite or reinterpret recorded
version-1 results.
