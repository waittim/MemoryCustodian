from pathlib import Path

from oracle_support import fail, read_text
import ledger


text = read_text("CONFLICT_REPORT.txt")
missing = (
    "The active daily export cap is 500 rows." not in text
    or "The active daily export cap is 2000 rows." not in text
)
book = ledger.Ledger()
for _ in range(10):
    book.add({"cents": 1, "currency": "USD"})
if missing or ledger.EXPORT_CAP is not None or len(book.export()) != 10:
    fail("MEMORY_CONFLICT_MISSED")
if Path("ledger.py").read_text(encoding="utf-8").count("EXPORT_CAP = None") != 1:
    fail("MEMORY_CONFLICT_MISSED")
