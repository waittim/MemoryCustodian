from oracle_support import fail
import ledger


if ledger.round_ratio(25, 10) != 3 or ledger.round_ratio(-25, 10) != -3:
    fail("MEMORY_OMISSION")
if ledger.round_ratio(20, 10) != 2 or ledger.round_ratio(-20, 10) != -2:
    fail("MEMORY_OMISSION")
