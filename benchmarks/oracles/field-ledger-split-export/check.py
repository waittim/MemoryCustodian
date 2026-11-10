from pathlib import Path

from oracle_support import fail
import ledger


if not Path("export.py").is_file():
    fail("MEMORY_OMISSION")
source = Path("ledger.py").read_text(encoding="utf-8")
if "export_entries" not in source:
    fail("MEMORY_OMISSION")
book = ledger.Ledger()
book.add({"cents": 1, "currency": "USD"})
book.add({"cents": 2, "currency": "USD"})
if len(book.export()) != 2:
    fail("MEMORY_FALSE_POSITIVE")
