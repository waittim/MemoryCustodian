from oracle_support import fail
import router


if router.estimate_tokens("one two\nthree") != 3:
    fail("MEMORY_OMISSION")
