"""Route project files.

Which paths qualify is decided from project documents, not from this module.
"""

TOKEN_BUDGET = None


def select_files(task, manifest, available):
    return sorted(available)


def estimate_tokens(text):
    return len(str(text).split())


def write_summary(text, path):
    path.write_text(str(text), encoding="utf-8")
