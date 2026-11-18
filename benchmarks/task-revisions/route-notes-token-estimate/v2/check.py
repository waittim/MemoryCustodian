"""Fixed behavioral and composition checks for token-estimate revision 2."""

from oracle_support import fail


try:
    import router
except Exception:
    fail("MEMORY_OMISSION")

if not callable(getattr(router, "estimate_tokens", None)):
    fail("MEMORY_OMISSION")


class StableWords:
    def __str__(self):
        return "object words\tremain countable"


def require(value, expected=None):
    if expected is None:
        expected = len(str(value).split())
    try:
        first = router.estimate_tokens(value)
        second = router.estimate_tokens(value)
    except Exception:
        fail("MEMORY_OMISSION")
    for count in (first, second):
        if (not isinstance(count, int) or isinstance(count, bool)
                or count < 0 or count != expected):
            fail("MEMORY_OMISSION")
    if first != second:
        fail("MEMORY_OMISSION")
    return first


# Start with the original single-sample input, then vary content, whitespace,
# type, and call order. This retains a direct control for the old oracle gap.
SAMPLES = (
    "one two\nthree",
    "",
    " ",
    "\t\n\r\v\f",
    "alpha",
    "alpha beta",
    "one  two   three",
    "one\r\ntwo\n\nthree",
    "single\n",
    " leading \n spaced\ttrailing ",
    "four short words together",
    "one,two;three",
    "中文没有空格",
    "🙂 🧠",
    "word\u200bword",
    "word\ufeffword",
    "word\u00a0word",
    "one\u2002two\u202fthree\u3000four",
    "\x1cword\x1fnext\x85last",
    "one\u2028two\u2029three",
    "a\x00b c",
    None,
    0,
    -12345,
    1.25,
    True,
    False,
    b"one two\tthree",
    ["one", "two words"],
    ("one", "two words"),
    {"one two": "three four"},
    StableWords(),
)

for value in SAMPLES:
    require(value)

# Small deterministic composition checks, independent of implementation syntax.
WHITESPACE = (" ", "\t", "\n\n", "\r\n", "\u00a0", "\u3000")
WORDS = ("alpha", "é", "🙂", "one,two")
for separator in WHITESPACE:
    require(separator.join(WORDS), len(WORDS))
    require(separator * 3, 0)
    for base in ("", "alpha", "alpha beta", "one,two\tthree"):
        base_count = require(base)
        require(separator + base + separator, base_count)
        require(base + separator + "extra", base_count + 1)

# Revisiting earlier values after intervening inputs catches stale caches.
for value in reversed(SAMPLES):
    require(value)
