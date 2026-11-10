"""Route project files.

Which paths qualify is decided from project documents, not from this module.
"""

import re

TOKEN_BUDGET = None


def select_files(task, manifest, available):
    return sorted(available)


def estimate_tokens(text):
    return len(str(text).splitlines())


def write_summary(text, path):
    redacted = re.sub(r"sk-[A-Za-z0-9]+", "[REDACTED]", str(text))
    path.write_text(redacted, encoding="utf-8")
