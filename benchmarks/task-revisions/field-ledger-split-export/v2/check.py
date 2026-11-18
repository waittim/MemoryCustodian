"""Behavior and executed-module checks for the public split-export v2 contract.

This is a development grader, not an adversarial execution or network sandbox.
"""

from copy import deepcopy
from pathlib import Path
import sys

from oracle_support import fail


EXPORT_PATH = Path("export.py").resolve()
if not EXPORT_PATH.is_file():
    fail("MEMORY_OMISSION")

try:
    import ledger
except Exception:
    fail("MEMORY_OMISSION")


def observed_export(book):
    returned_lists = []

    def observe(frame, event, value):
        if event == "return" and isinstance(value, list):
            if Path(frame.f_code.co_filename).resolve() == EXPORT_PATH:
                returned_lists.append(value)

    previous = sys.getprofile()
    try:
        sys.setprofile(observe)
        result = book.export()
    except Exception:
        fail("MEMORY_FALSE_POSITIVE")
    finally:
        sys.setprofile(previous)
    if not any(value is result for value in returned_lists):
        fail("MEMORY_OMISSION")
    return result


SAMPLES = (
    (),
    ({"cents": 1, "currency": "USD", "memo": "first", "tags": ["local"]},),
    (
        {"cents": 1, "currency": "USD", "memo": "first", "tags": ["local"]},
        {"cents": 2, "currency": "EUR", "memo": "second", "extra": {"kept": True}},
        {"cents": -3, "currency": "JPY", "memo": "third", "tags": []},
    ),
)

for sample in SAMPLES:
    try:
        book = ledger.Ledger()
        for entry in sample:
            book.add(deepcopy(entry))
        original_entries = book.entries
        original_rows = list(original_entries)
        original_contents = deepcopy(original_entries)
    except Exception:
        fail("MEMORY_FALSE_POSITIVE")
    # Reuse the module and ledger while changing the cap, including after a
    # helper's first import. Import-time copies of the cap must not freeze it.
    for cap in (None, 0, 1, len(sample), len(sample) + 1, -1, None):
        ledger.EXPORT_CAP = cap
        expected = original_rows if cap is None else original_rows[:cap]
        first = observed_export(book)
        second = observed_export(book)
        if (
            not isinstance(first, list)
            or not isinstance(second, list)
            or first is original_entries
            or second is original_entries
            or first is second
            or first != expected
            or second != expected
            or any(row is not wanted for row, wanted in zip(first, expected))
            or any(row is not wanted for row, wanted in zip(second, expected))
            or book.entries is not original_entries
            or book.entries != original_contents
            or any(row is not wanted for row, wanted in zip(book.entries, original_rows))
            or ledger.EXPORT_CAP != cap
        ):
            fail("MEMORY_FALSE_POSITIVE")
        first.append({"oracle-only": True})
        first.reverse()
        if book.entries != original_contents or second != expected:
            fail("MEMORY_FALSE_POSITIVE")
