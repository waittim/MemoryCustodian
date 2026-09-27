#!/usr/bin/env python3
"""Check that platform adapters point at one Protocol 0.8 contract.

This is intentionally a static repository check. It does not start an agent,
invoke a platform runtime, or claim semantic correctness.
"""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = (
    "adapters/codex/AGENTS.snippet.md",
    "adapters/claude-code/CLAUDE.snippet.md",
    "adapters/gemini/GEMINI.snippet.md",
    "adapters/generic/agent-instructions.md",
)

REQUIRED = (
    ("protocol", "Protocol 0.8"),
    ("manifest-first loading", "manifest.md"),
    ("brief loading", "brief.md"),
    ("canonical task", "canonical task"),
    ("planned scope", "touched/planned"),
    ("strict routing", "strict-routing"),
    ("incomplete routing gate", "INCOMPLETE"),
    ("ambiguous routing gate", "AMBIGUOUS"),
    ("invalid routing gate", "INVALID"),
    ("archive boundary", "archive/"),
    ("inbox boundary", "inbox.md"),
    ("transaction audit", "audit --transactions"),
    ("recovery workflow", "recover"),
    ("JSON output", "--format json"),
    ("canonical erasure scope", "erasure_scope"),
    ("history boundary", "Git history"),
    ("distributed-copy boundary", "distributed copies"),
)

FORBIDDEN_ROUTING_TABLES = (
    "## Load by task",
    "### Planning / architecture / refactoring",
    "### Optional module index",
    "exclusive-group",
)

ROUTE_COMMAND = re.compile(
    r"memory-custodian\s+read\s+--task\s+<TASK>.*--strict-routing.*--path\s+<PATH>.*--explain",
    flags=re.DOTALL,
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def check() -> list[str]:
    issues: list[str] = []
    for relative in ADAPTERS:
        path = ROOT / relative
        if not path.exists():
            issues.append(f"{relative}: missing adapter")
            continue
        text = _read(relative).replace("\r\n", "\n").replace("\r", "\n")
        collapsed = re.sub(r"\s+", " ", text).casefold()
        for label, term in REQUIRED:
            if term.casefold() not in collapsed:
                issues.append(f"{relative}: missing {label} contract ({term!r})")
        if not ROUTE_COMMAND.search(text):
            issues.append(f"{relative}: missing canonical shared read command")
        for marker in FORBIDDEN_ROUTING_TABLES:
            if marker.casefold() in text.casefold():
                issues.append(f"{relative}: embeds a second routing table ({marker})")

        # Adapters may explain their platform entry point, but must not contain
        # a second implementation of the protocol's controlled vocabulary.
        if text.count("canonical task") > 2:
            issues.append(f"{relative}: repeats canonical-task policy; use the shared router")
        if "Subject registry" in text and "shared" not in text.casefold():
            issues.append(f"{relative}: appears to define a local Subject registry")

    return issues


def main() -> int:
    issues = check()
    if issues:
        print("MemoryCustodian adapter contract check: FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("MemoryCustodian adapter contract check: OK")
    print(f"Adapters: {len(ADAPTERS)}")
    print("Static check only; no live-agent benchmark was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
