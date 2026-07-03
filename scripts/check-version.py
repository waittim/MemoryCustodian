#!/usr/bin/env python3
"""Check version fields declared in .version-bump.json."""

from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".version-bump.json"


def _json_path(data, path: str):
    value = data
    for part in path.split("."):
        if isinstance(value, list):
            value = value[int(part)]
        else:
            value = value[part]
    return str(value)


def _read_entry(entry: dict[str, str]) -> str:
    path = ROOT / entry["path"]
    if "json_path" in entry:
        return _json_path(json.loads(path.read_text(encoding="utf-8")), entry["json_path"])
    text = path.read_text(encoding="utf-8")
    match = re.search(entry["regex"], text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"{entry['path']}: regex did not match")
    return match.group(1)


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    failed = False
    for group, entries in config["groups"].items():
        values: list[tuple[str, str]] = []
        for entry in entries:
            values.append((entry["path"], _read_entry(entry)))
        unique = sorted({value for _path, value in values})
        print(f"{group}:")
        for path, value in values:
            print(f"- {path}: {value}")
        if len(unique) == 1:
            print(f"  OK: {unique[0]}")
        else:
            print(f"  DRIFT: {', '.join(unique)}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
