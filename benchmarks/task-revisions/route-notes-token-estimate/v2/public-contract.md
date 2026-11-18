# Token-estimate revision 2: public acceptance contract

Correct `router.estimate_tokens(text)` to preserve the reference behavior
`len(str(text).split())`. This project's estimate counts whitespace-delimited
words; it is not a model tokenizer or an estimate of a provider's billed usage.

The observable contract is:

- Convert the input with Python's `str(text)` first. Inputs with a stable,
  successful string conversion are supported, including strings, numbers,
  booleans, `None`, containers, bytes, and objects with a stable `__str__`.
- Count the nonempty runs separated by Python whitespace, using the same
  whitespace semantics as `str.split()` without an explicit separator.
  Consecutive spaces, tabs, newlines, carriage returns, and Unicode whitespace
  are separators; leading and trailing whitespace does not add words.
- Empty or whitespace-only text has count zero. Repeated newlines do not add
  words. Punctuation and letters within an uninterrupted non-whitespace run
  remain one word. Zero-width space (`U+200B`) and a byte-order mark (`U+FEFF`)
  are not whitespace under this contract.
- Return a nonnegative Python `int`, excluding `bool`. A floating-point value
  numerically equal to the count is not an integer result. For inputs with a
  stable string representation, repeated calls give the same count, regardless
  of intervening calls on other inputs.

No sorting, line-counting, or character-counting approximation can replace
these semantics. Valid implementations include `str.split()`, a Unicode-aware
regular expression over non-whitespace runs, and a manual state machine based
on `str.isspace()`. The oracle does not require a particular expression, import,
source-code spelling, or AST shape.

The development oracle uses fixed varied inputs and small, predetermined
composition checks: adding whitespace preserves the count, joining word runs
with whitespace preserves their number, and appending one separated word adds
one. It also checks string conversion, result type, and repeated calls. Cases
are chosen before result collection and do not use random or model feedback.

These finite development checks are not a security boundary or a proof against
arbitrary cheating. They cannot prove every custom object's behavior or the
correctness of all possible input strings. Stateful or failing `__str__`
implementations are outside the stable-input samples.

Revision 2 is independent of the original task, fixture, reference, oracle,
and recorded experiments. Keep its outcomes separately identified; do not
overwrite or reinterpret version-1 results using this contract.
