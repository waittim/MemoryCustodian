from oracle_support import fail
import ledger


book = ledger.Ledger()
try:
    book.add({"cents": -1, "currency": "USD"})
except ValueError:
    rejected = True
else:
    rejected = False
if not rejected:
    fail("MEMORY_OMISSION")
book.add({"cents": 1, "currency": "USD"})
if len(book.entries) != 1:
    fail("MEMORY_OMISSION")
