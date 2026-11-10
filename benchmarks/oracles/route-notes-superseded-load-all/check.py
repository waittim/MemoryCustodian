from oracle_support import fail
import router


available = ["docs/a.md", "docs/b.md", "docs/extra.md"]
manifest = {"tasks": {"billing": ["docs/a.md"]}}
got = router.select_files("billing", manifest, available)
if got == sorted(available):
    fail("MEMORY_STALE_USE")
if got != ["docs/a.md"]:
    fail("MEMORY_OMISSION")
