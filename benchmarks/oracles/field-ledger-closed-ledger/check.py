from oracle_support import fail
import ledger


book = ledger.Ledger(closed=True)
try:
    book.add({"cents": 1, "currency": "USD"})
except ValueError:
    rejected = True
else:
    rejected = False
if not rejected:
    fail("MEMORY_OMISSION")
open_book = ledger.Ledger()
open_book.add({"cents": 1, "currency": "USD"})
if len(open_book.entries) != 1:
    fail("MEMORY_OMISSION")
