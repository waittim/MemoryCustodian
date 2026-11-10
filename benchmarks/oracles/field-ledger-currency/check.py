from oracle_support import fail
import ledger


try:
    normalized = ledger.normalize_currency("usd")
except ValueError:
    fail("MEMORY_OMISSION")
if normalized == "$":
    fail("MEMORY_FALSE_POSITIVE")
if normalized != "USD":
    fail("MEMORY_OMISSION")
try:
    ledger.normalize_currency("$")
except ValueError:
    pass
else:
    fail("MEMORY_OMISSION")
