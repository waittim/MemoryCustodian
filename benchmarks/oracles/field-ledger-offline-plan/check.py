from oracle_support import fail, read_text


text = read_text("PLAN.md")
if "Production export stays on the local machine and does not use the network." not in text:
    fail("MEMORY_OMISSION")
lowered = text.casefold()
if "urllib" in lowered or "socket" in lowered or "requests" in lowered:
    fail("MEMORY_AUTHORITY_VIOLATION")
