"""Check the published, line-based no-prose-area revision-2 contract."""

from oracle_support import fail, read_text


RULES = (
    "Do not infer an area from prose.",
    "Load an area file only when the task explicitly names that area.",
)
SKIP_ACTION = "skip areas/billing.md"
LOAD_ACTION = "load areas/billing.md"


text = read_text("PLAN.md")
if any(rule not in text for rule in RULES):
    fail("MEMORY_OMISSION")

lines = {line.strip() for line in text.splitlines()}
if LOAD_ACTION in lines:
    fail("MEMORY_FALSE_POSITIVE")
if SKIP_ACTION not in lines:
    fail("MEMORY_OMISSION")
