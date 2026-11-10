"""Route project files.

Which paths qualify is decided from project documents, not from this module.
"""

TOKEN_BUDGET = None


def _is_archive(path):
    normalized = str(path).replace("\\", "/").strip("/")
    return (
        normalized == "archive"
        or normalized.startswith("archive/")
        or "/archive/" in f"/{normalized}"
    )


def select_files(task, manifest, available):
    listed = manifest.get("tasks", {}).get(task, [])
    available_set = set(available)
    selected = [
        path
        for path in listed
        if path in available_set and not _is_archive(path)
    ]
    return sorted(selected)


def estimate_tokens(text):
    return len(str(text).splitlines())


def write_summary(text, path):
    path.write_text(str(text), encoding="utf-8")
