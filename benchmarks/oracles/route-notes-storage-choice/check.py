from oracle_support import fail, read_text


text = read_text("PLAN.md")
for sentence in (
    "Routing rules stay in the manifest.",
    "Do not store routing rules in a database.",
    "Do not copy routing rules into the bootstrap file.",
):
    if sentence not in text:
        fail("MEMORY_OMISSION")
