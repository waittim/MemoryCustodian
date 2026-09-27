"""Shared structured command results and finding registry.

Protocol 0.8 deliberately keeps the human renderer as a view of the same
objects that are exposed through ``--format json``.  Command modules should
build :class:`CommandResult` values and never make another command recover
meaning by scraping human output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


SEVERITIES = ("INFO", "WARNING", "ERROR", "BLOCKER")


@dataclass(frozen=True)
class Finding:
    """One stable, public finding shared by text and JSON renderers."""

    code: str
    severity: str
    path: str
    entry_id: str | None
    message: str
    remediation: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def canonical(self) -> dict[str, Any]:
        value = asdict(self)
        # Keep the six required public fields at the top level.  Details are
        # optional structured identity (Subject/Facet/reconciliation data),
        # never a second free-form payload.
        if self.details:
            value["details"] = dict(sorted(self.details.items()))
        else:
            value.pop("details", None)
        return value


@dataclass(frozen=True)
class CommandResult:
    """Immutable source of truth for one command outcome.

    Process exit status is deliberately *not* accepted as an independent
    input.  It is derived from the same findings that produce ``status`` and
    ``exit_class`` so public machine state cannot contradict the process
    state.  ``fatal`` distinguishes an invocation/environment failure from a
    project blocker; both return 2, but only the former uses the ``fatal``
    exit class.
    """

    command: str
    protocol_version: str | None
    data: Mapping[str, Any] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    rendered_text: str = ""
    disclaimers: tuple[str, ...] = ()
    fatal: bool = False

    def __post_init__(self) -> None:
        invalid = sorted({item.severity for item in self.findings} - set(SEVERITIES))
        if invalid:
            raise ValueError(
                "CommandResult contains unsupported finding severity: "
                + ", ".join(invalid)
            )
        if self.fatal and not any(
            item.severity in {"ERROR", "BLOCKER"} for item in self.findings
        ):
            raise ValueError("A fatal CommandResult must contain an ERROR or BLOCKER finding.")

    @property
    def ordered_findings(self) -> tuple[Finding, ...]:
        return tuple(sorted(
            self.findings,
            key=lambda item: (
                SEVERITIES.index(item.severity) if item.severity in SEVERITIES else 99,
                item.code,
                item.path,
                item.entry_id or "",
                item.message,
            ),
        ))

    @property
    def return_code(self) -> int:
        if self.fatal:
            return 2
        if any(item.severity == "BLOCKER" for item in self.findings):
            return 2
        if any(item.severity == "ERROR" for item in self.findings):
            return 1
        return 0

    @property
    def status(self) -> str:
        if any(item.severity in {"ERROR", "BLOCKER"} for item in self.findings):
            return "FAIL"
        if any(item.severity == "WARNING" for item in self.findings):
            return "REVIEW"
        return "PASS"

    @property
    def exit_class(self) -> str:
        if self.fatal:
            return "fatal"
        if any(item.severity == "BLOCKER" for item in self.findings):
            return "blocker"
        if any(item.severity == "ERROR" for item in self.findings):
            return "domain-failure"
        return "success-with-review" if self.status == "REVIEW" else "success"

    def validate(self) -> None:
        """Fail closed if a future edit breaks the public outcome matrix."""

        expected = {
            "success": ("PASS", 0),
            "success-with-review": ("REVIEW", 0),
            "domain-failure": ("FAIL", 1),
            "blocker": ("FAIL", 2),
            "fatal": ("FAIL", 2),
        }[self.exit_class]
        actual = (self.status, self.return_code)
        if actual != expected:
            raise ValueError(
                "Inconsistent command result: "
                f"exit_class={self.exit_class!r} requires {expected!r}, got {actual!r}."
            )

    def payload(self, *, output_schema_version: int = 1) -> dict[str, Any]:
        self.validate()
        data = dict(self.data)
        data.setdefault("rendered_text", self.rendered_text)
        return {
            "output_schema_version": output_schema_version,
            "command": self.command,
            "protocol_version": self.protocol_version,
            "status": self.status,
            "exit_class": self.exit_class,
            "data": data,
            "findings": [item.canonical() for item in self.ordered_findings],
            "disclaimers": list(self.disclaimers),
        }


def stable_path(
    value: str | Path | None,
    *,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
    private_alias: str = "private/state",
) -> str:
    """Return a repo-relative or stable private alias, never a machine path."""

    if value is None:
        return ""
    text = str(value).replace("\\", "/")
    if not text:
        return ""
    # Already-public aliases are intentionally preserved.
    if text.startswith(("private/", "local/", "repo/")):
        return text
    candidate = Path(value)
    if not candidate.is_absolute() and project_root is not None and memory_dir is not None:
        memory_relative = candidate.as_posix().removeprefix("./")
        known_memory_roots = {
            "manifest.md", "subjects.md", "brief.md", "decisions.md",
            "constraints.md", "do-not-use.md", "inbox.md", "preferences.md",
            "changelog.md", "reconciliations.md", "archive", "areas", "rules",
            "profiles",
        }
        first = memory_relative.split("/", 1)[0]
        if first in known_memory_roots:
            try:
                return (memory_dir / memory_relative).resolve(strict=False).relative_to(
                    project_root.resolve()
                ).as_posix()
            except (OSError, ValueError):
                return "docs/memory/" + memory_relative
    roots = [root for root in (project_root, memory_dir) if root is not None]
    for root in roots:
        try:
            relative = candidate.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        if root == project_root:
            return relative or "."
        return f"docs/memory/{relative}" if relative else "docs/memory"
    if candidate.is_absolute() or re.match(r"^[A-Za-z]:/", text):
        return private_alias
    # Callers normally pass a repo-relative path.  Strip the common leading
    # ./ without resolving it so custom memory paths remain deterministic.
    return text.removeprefix("./")


def sanitize_text(
    text: str,
    *,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> str:
    """Redact absolute project/private paths from public text defensively."""

    result = text
    for root in (project_root, memory_dir):
        if root is None:
            continue
        raw = str(root)
        result = result.replace(raw, stable_path(root, project_root=project_root, memory_dir=memory_dir))
    # A path outside the project must not escape through rendered diagnostics.
    result = re.sub(
        r"(?<![A-Za-z0-9_])/(?:private|var|tmp|Users|home|Volumes|opt|workspace)/[^\s,;:)]+",
        "private/state",
        result,
    )
    result = re.sub(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s,;:)]+", "private/state", result)
    return result


def make_finding(
    code: str,
    severity: str,
    message: str,
    *,
    path: str | Path | None = "docs/memory",
    entry_id: str | None = None,
    remediation: str = "Review the referenced managed-memory source and run audit again.",
    details: Mapping[str, Any] | None = None,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> Finding:
    if severity not in SEVERITIES:
        raise ValueError(f"Unsupported finding severity: {severity}")
    return Finding(
        code=code,
        severity=severity,
        path=stable_path(path, project_root=project_root, memory_dir=memory_dir),
        entry_id=entry_id,
        message=sanitize_text(message, project_root=project_root, memory_dir=memory_dir),
        remediation=sanitize_text(remediation, project_root=project_root, memory_dir=memory_dir),
        details=dict(details or {}),
    )


def unique_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    def freeze(value: Any):
        if isinstance(value, Mapping):
            return tuple(sorted((str(key), freeze(item)) for key, item in value.items()))
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(freeze(item) for item in value)
        return value

    values = {
        (
            item.code,
            item.severity,
            item.path,
            item.entry_id,
            item.message,
            freeze(item.details),
        ): item
        for item in findings
    }
    return tuple(sorted(
        values.values(),
        key=lambda item: (
            SEVERITIES.index(item.severity) if item.severity in SEVERITIES else 99,
            item.code,
            item.path,
            item.entry_id or "",
            item.message,
        ),
    ))


def render_findings(title: str, result: CommandResult, *, prefix: str = "") -> str:
    """Render a stable human view without changing the underlying result."""

    lines = [f"{prefix}{title}: {result.status}"]
    if result.protocol_version is not None:
        lines.append(f"Protocol: {result.protocol_version}")
    for key, value in result.data.items():
        if key in {"rendered_text", "protocol_version", "files", "subjects", "entries", "findings"}:
            continue
        if isinstance(value, (str, int, bool)):
            label = key.replace("_", " ").capitalize()
            lines.append(f"{label}: {value}")
    lines.append("Findings:")
    if not result.ordered_findings:
        lines.append("- none")
    else:
        lines.extend(
            f"- {item.code} {item.severity}: {item.message}"
            for item in result.ordered_findings
        )
    return "\n".join(lines) + "\n"
