"""Helper imported by hidden oracles. It is not copied into agent checkouts."""

from __future__ import annotations

import sys


def fail(*labels: str) -> None:
    for label in labels:
        print(f"LABEL {label}")
    raise SystemExit(1)


def read_text(path: str) -> str:
    from pathlib import Path

    file_path = Path(path)
    if not file_path.is_file():
        return ""
    return file_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(0)
