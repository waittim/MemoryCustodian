"""Deterministic, redacted privacy and credential-pattern scanning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str
    severity: str
    preview: str
    category: str


SECURITY_PATTERNS = (
    ("private-key", "ERROR", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github-token", "ERROR", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("aws-access-key", "ERROR", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("openai-key", "ERROR", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-key", "ERROR", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("bearer-token", "ERROR", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b", re.I)),
    ("credential-assignment", "WARNING", re.compile(r"\b(?:password|secret|api_key)\s*=\s*[^\s#]+", re.I)),
    ("dotenv-credential", "WARNING", re.compile(r"^\s*[A-Z][A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*\S+")),
    ("credential-url", "ERROR", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", re.I)),
)
PRIVACY_PATTERNS = (
    (
        "machine-path",
        "WARNING",
        re.compile(r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|/Volumes/[^/\s]+/|C:\\Users\\[^\\\s]+\\)"),
    ),
    ("personal-email", "WARNING", re.compile(r"\b[A-Z0-9._%+-]+@(?!example\.com\b)[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone-number", "WARNING", re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)")),
)
UUID_PATTERN = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![0-9a-f])",
    re.I,
)


def _matches(line: str, kind: str, pattern: re.Pattern[str]):
    matches = pattern.finditer(line)
    if kind != "phone-number":
        return matches
    # A generated project UUID can contain 10–15 digits separated by hyphens.
    # Ignore only phone-pattern spans inside UUIDs; keep real numbers on the
    # same line detectable and redacted.
    identities = tuple(match.span() for match in UUID_PATTERN.finditer(line))
    return (
        match for match in matches
        if not any(match.start() < end and match.end() > start for start, end in identities)
    )


def _redact(line: str) -> str:
    """Redact every recognized sensitive span before any line preview is emitted."""

    spans = [
        (match.start(), match.end())
        for kind, _severity, pattern in (*SECURITY_PATTERNS, *PRIVACY_PATTERNS)
        for match in _matches(line, kind, pattern)
    ]
    if not spans:
        return line.strip()[:120]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    parts: list[str] = []
    cursor = 0
    for start, end in merged:
        parts.extend((line[cursor:start], "[redacted]"))
        cursor = end
    parts.append(line[cursor:])
    return "".join(parts).strip()[:120]


def scan_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for category, patterns in (("security", SECURITY_PATTERNS), ("privacy", PRIVACY_PATTERNS)):
            for kind, severity, pattern in patterns:
                match = next(iter(_matches(line, kind, pattern)), None)
                if match:
                    findings.append(Finding(path, number, kind, severity, _redact(line), category))
    return findings
