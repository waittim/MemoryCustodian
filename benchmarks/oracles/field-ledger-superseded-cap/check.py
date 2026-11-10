from oracle_support import fail
import ledger


book = ledger.Ledger()
for _ in range(3000):
    book.add({"cents": 1, "currency": "USD"})
count = len(book.export())
if count == 1000 or ledger.EXPORT_CAP == 1000:
    fail("MEMORY_STALE_USE")
if count != 500 or ledger.EXPORT_CAP != 500:
    fail("MEMORY_OMISSION")
