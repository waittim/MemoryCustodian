#!/usr/bin/env python3
"""Run the offline MemoryCustodian benchmark harness."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners.harness import main


if __name__ == "__main__":
    raise SystemExit(main())
