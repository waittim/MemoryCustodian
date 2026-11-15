from oracle_support import fail
import router


available = ["docs/a.md", "docs/archive/old.md", "docs/extra.md"]
manifest = {"tasks": {"billing": ["docs/a.md", "docs/archive/old.md"]}}
got = router.select_files("billing", manifest, available)
if got != ["docs/a.md"]:
    fail("MEMORY_OMISSION")
