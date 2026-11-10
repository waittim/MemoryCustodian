from oracle_support import fail
import router


available = ["docs/a.md", "docs/b.md", "docs/extra.md", "docs/archive/old.md"]
manifest = {"tasks": {"billing": ["docs/b.md", "docs/a.md"]}}
got = router.select_files("billing", manifest, available)
if got != ["docs/a.md", "docs/b.md"]:
    fail("MEMORY_OMISSION")
