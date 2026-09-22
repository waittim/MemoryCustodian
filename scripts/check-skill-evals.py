#!/usr/bin/env python3
"""Check MemoryCustodian static scenarios and core skill contracts."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "memory-custodian" / "eval-manifest.json"
ADAPTERS = (
    "adapters/codex/AGENTS.snippet.md",
    "adapters/claude-code/CLAUDE.snippet.md",
    "adapters/gemini/GEMINI.snippet.md",
    "adapters/generic/agent-instructions.md",
)
CROSS_AGENT_FIXTURE = ROOT / "evals" / "memory-custodian" / "cross-agent" / "shared-contract.json"
LIVE_EVALUATION = ROOT / "evals" / "memory-custodian" / "live-evaluation.md"


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


def _check_adapters() -> list[str]:
    issues: list[str] = []
    forbidden = ("## Load by task", "### Planning / architecture / refactoring")
    for relative in ADAPTERS:
        path = ROOT / relative
        if not path.exists():
            issues.append(f"{relative}: missing adapter")
            continue
        text = _read_text(path)
        if "canonical task" not in text.casefold() or "touched/planned" not in text:
            issues.append(f"{relative}: missing explicit task/scope workflow")
        if "strict-routing" not in text:
            issues.append(f"{relative}: missing shared strict-routing invocation")
        for marker in forbidden:
            if marker in text:
                issues.append(f"{relative}: embeds a second routing table ({marker})")
    return issues


def _check_cross_agent_fixture() -> list[str]:
    issues: list[str] = []
    if not CROSS_AGENT_FIXTURE.exists():
        return ["evals/memory-custodian/cross-agent/shared-contract.json: missing fixture"]
    try:
        fixture = json.loads(_read_text(CROSS_AGENT_FIXTURE))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{CROSS_AGENT_FIXTURE.relative_to(ROOT)}: invalid JSON: {exc}"]
    if fixture.get("agents") != ["codex", "claude-code", "gemini", "generic"]:
        issues.append("cross-agent fixture must cover the four supported adapters in stable order")
    required = {
        "file_set", "skipped_module_set", "entry_set", "order",
        "routing_completeness", "reason_codes", "warnings",
        "context_sha256_field", "subject_ids_field", "conflict_status",
        "conflict_findings", "reconciliation_findings", "erasure_scope_field",
    }
    contract = fixture.get("expected_contract", {})
    missing = sorted(required - set(contract)) if isinstance(contract, dict) else sorted(required)
    if missing:
        issues.append("cross-agent fixture missing expected fields: " + ", ".join(missing))
    if not LIVE_EVALUATION.exists() or "not a claim" not in _read_text(LIVE_EVALUATION):
        issues.append("live cross-agent evaluation recipe must remain explicit and non-aspirational")
    return issues


def main() -> int:
    config = json.loads(_read_text(MANIFEST))
    issues = _check_skill_contract(config)
    issues.extend(_check_scenarios(config))
    issues.extend(_check_adapters())
    issues.extend(_check_cross_agent_fixture())

    if issues:
        print("MemoryCustodian skill contract check: FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("MemoryCustodian skill contract check: OK")
    print(f"Scenarios: {len(config['required_scenarios'])}")
    print(f"Skill contracts: {len(config['skill_contract'])}")
    print(f"Adapter contracts: {len(ADAPTERS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
