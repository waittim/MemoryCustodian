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
    ("machine-path", "WARNING", re.compile(r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|C:\\Users\\[^\\\s]+\\)")),
    ("personal-email", "WARNING", re.compile(r"\b[A-Z0-9._%+-]+@(?!example\.com\b)[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone-number", "WARNING", re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)")),
)


def _redact(line: str, match: re.Match[str]) -> str:
    value = match.group(0)
    masked = (value[:3] + "…" + value[-2:]) if len(value) > 7 else "[redacted]"
    rendered = line[: match.start()] + masked + line[match.end() :]
    return rendered.strip()[:120]


def scan_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for category, patterns in (("security", SECURITY_PATTERNS), ("privacy", PRIVACY_PATTERNS)):
            for kind, severity, pattern in patterns:
                match = pattern.search(line)
                if match:
                    findings.append(Finding(path, number, kind, severity, _redact(line, match), category))
    return findings
