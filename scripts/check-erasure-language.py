#!/usr/bin/env python3
"""Reject unbounded erasure claims in public MemoryCustodian documentation."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    ROOT / "README.md",
    ROOT / "RELEASE-NOTES.md",
    ROOT / "skills" / "memory-custodian",
    ROOT / "adapters",
)

# These patterns identify a positive claim, not the documented prohibition
# (for example, "Never describe ... as permanent deletion everywhere").
FORBIDDEN = (
    re.compile(r"\b(?:is|was|are|were|has been|will be)\s+permanently\s+(?:deleted|erased|removed)\b", re.I),
    re.compile(r"\b(?:is|was|are|were|has been|will be)\s+completely\s+(?:deleted|erased|removed)\b", re.I),
    re.compile(r"\b(?:permanently|completely)\s+(?:deleted|erased|removed)\s+everywhere\b", re.I),
    re.compile(r"\b(?:removed|erased|deleted)\s+from\s+all\s+(?:clones|forks|copies|backups)\b", re.I),
    re.compile(r"\b(?:no|zero)\s+(?:reachable\s+)?copies?\s+remain\b", re.I),
    re.compile(r"\b(?:guarantees?|proves?)\s+(?:complete\s+)?erasure\b", re.I),
    re.compile(r"\b(?:guarantees?|proves?)\s+(?:that\s+)?(?:no|zero)\s+copies?\b", re.I),
)

BOUNDARY_TERMS = (
    "Git history",
    "distributed copies",
    "not a guarantee of erasure",
)


def _files() -> list[Path]:
    result: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            result.append(root)
        elif root.exists():
            result.extend(path for path in root.rglob("*.md") if path.is_file())
    return sorted(set(result))


def _is_negative(line: str) -> bool:
    lowered = line.casefold()
    return any(
        marker in lowered
        for marker in (
            "never describe",
            "do not claim",
            "does not guarantee",
            "neither mode guarantees",
            "neither guarantees",
            "not a guarantee",
            "not proof",
            "cannot prove",
        )
    )


def check() -> list[str]:
    issues: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for index, line in enumerate(lines):
            line_number = index + 1
            context = " ".join(lines[max(0, index - 1): min(len(lines), index + 2)])
            if _is_negative(context):
                continue
            for pattern in FORBIDDEN:
                match = pattern.search(line)
                if match:
                    relative = path.relative_to(ROOT).as_posix()
                    issues.append(f"{relative}:{line_number}: unbounded erasure claim: {match.group(0)!r}")
                    break

    # Public-facing surfaces must carry the positive boundary, so a later edit
    # cannot accidentally remove every caveat while keeping only the operation
    # verbs. References may carry the normative wording; adapters must carry a
    # short version because they are often the only loaded file.
    required_surfaces = (
        ROOT / "README.md",
        ROOT / "skills" / "memory-custodian" / "SKILL.md",
        ROOT / "skills" / "memory-custodian" / "references" / "platform-adapters.md",
    )
    for path in required_surfaces:
        text = path.read_text(encoding="utf-8")
        normalized = " ".join(text.casefold().split())
        missing = [term for term in BOUNDARY_TERMS if " ".join(term.casefold().split()) not in normalized]
        if missing:
            issues.append(f"{path.relative_to(ROOT).as_posix()}: missing bounded-erasure wording: {', '.join(missing)}")

    return issues


def main() -> int:
    issues = check()
    if issues:
        print("MemoryCustodian erasure-language check: FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("MemoryCustodian erasure-language check: OK")
    print(f"Scanned Markdown files: {len(_files())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
