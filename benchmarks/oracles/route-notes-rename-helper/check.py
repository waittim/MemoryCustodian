from pathlib import Path

from oracle_support import fail
import router


source = Path("router.py").read_text(encoding="utf-8")
if "def select_for_task" not in source:
    fail("MEMORY_OMISSION")
if source.count("sorted(available)") != 1:
    fail("MEMORY_FALSE_POSITIVE")
available = ["b.md", "a.md"]
if router.select_for_task("t", {}, available) != ["a.md", "b.md"]:
    fail("MEMORY_OMISSION")
if router.select_files("t", {}, available) != ["a.md", "b.md"]:
    fail("MEMORY_OMISSION")
