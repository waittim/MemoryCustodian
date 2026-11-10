from oracle_support import fail, read_text
import router


text = read_text("CONFLICT_REPORT.txt")
missing = (
    "The active token budget is 400." not in text
    or "The active token budget is 900." not in text
)
if missing or router.TOKEN_BUDGET is not None:
    fail("MEMORY_CONFLICT_MISSED")
