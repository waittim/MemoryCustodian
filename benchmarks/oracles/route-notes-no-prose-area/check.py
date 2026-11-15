from oracle_support import fail, read_text


text = read_text("PLAN.md")
if "Do not infer an area from prose." not in text:
    fail("MEMORY_OMISSION")
if "Load an area file only when the task explicitly names that area." not in text:
    fail("MEMORY_OMISSION")
if "skip areas/billing.md" not in text or "load areas/billing.md" in text:
    fail("MEMORY_FALSE_POSITIVE" if "load areas/billing.md" in text else "MEMORY_OMISSION")
