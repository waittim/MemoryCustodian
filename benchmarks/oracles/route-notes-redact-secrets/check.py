from pathlib import Path

from oracle_support import fail
import router


dest = Path("summary.txt")
router.write_summary("prefix sk-abc123 suffix", dest)
text = dest.read_text(encoding="utf-8")
if "sk-abc123" in text or "[REDACTED]" not in text:
    fail("MEMORY_OMISSION")
if "prefix" not in text or "suffix" not in text:
    fail("MEMORY_OMISSION")
