#!/usr/bin/env python3
"""Check MemoryCustodian skill eval scenarios and core skill contracts."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "memory-custodian" / "eval-manifest.json"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_section(text: str, heading: str) -> bool:
    return any(line.strip() == heading for line in text.splitlines())


def _section_body(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    body: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section:
            body.append(line)
    return body


def _has_bullet(text: str, heading: str) -> bool:
    return any(line.lstrip().startswith("- ") for line in _section_body(text, heading))


def _check_skill_contract(config: dict) -> list[str]:
    skill_path = ROOT / config["skill"]
    issues: list[str] = []
    if not skill_path.exists():
        return [f"{config['skill']}: missing skill file"]

    skill_text = _read_text(skill_path)
    for contract in config["skill_contract"]:
        missing = [term for term in contract["terms"] if term not in skill_text]
        if missing:
            joined = ", ".join(repr(term) for term in missing)
            issues.append(f"{config['skill']}: contract {contract['id']} missing {joined}")
    return issues


def _check_scenarios(config: dict) -> list[str]:
    scenarios_dir = ROOT / config["scenarios_dir"]
    issues: list[str] = []
    if not scenarios_dir.exists():
        return [f"{config['scenarios_dir']}: missing scenarios directory"]

    for scenario_id in config["required_scenarios"]:
        relative = f"{config['scenarios_dir']}/{scenario_id}.md"
        path = ROOT / relative
        if not path.exists():
            issues.append(f"{relative}: missing required scenario")
            continue

        text = _read_text(path)
        for heading in config["required_sections"]:
            if not _has_section(text, heading):
                issues.append(f"{relative}: missing section {heading}")
        for heading in ("## Required Observations", "## Forbidden Outcomes"):
            if _has_section(text, heading) and not _has_bullet(text, heading):
                issues.append(f"{relative}: {heading} must contain bullet checks")
    return issues


def main() -> int:
    config = json.loads(_read_text(MANIFEST))
    issues = _check_skill_contract(config)
    issues.extend(_check_scenarios(config))

    if issues:
        print("MemoryCustodian skill eval check: FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("MemoryCustodian skill eval check: OK")
    print(f"Scenarios: {len(config['required_scenarios'])}")
    print(f"Skill contracts: {len(config['skill_contract'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
