"""Stable public output envelopes for Protocol 0.8 commands.

Command implementations publish typed data and findings while producing their
human view. The JSON renderer consumes those values directly; it never
recovers contract fields by parsing human-readable stdout.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from .context_result import context_sha256
from .protocol import (
    parse_version,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
    strict_protocol_metadata,
)
from .results import CommandResult, Finding, make_finding, sanitize_text, unique_findings


OUTPUT_SCHEMA_VERSION = 1
PUBLIC_PLAN_SCHEMA_VERSION = 1


class ResultContractError(RuntimeError):
    """Raised when a handler's legacy exit code contradicts its typed result."""


@dataclass
class CommandMetadata:
    """Typed fields published during one command execution."""

    data: dict[str, object] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    disclaimers: list[str] = field(default_factory=list)


_ACTIVE_METADATA: ContextVar[CommandMetadata | None] = ContextVar(
    "memory_custodian_command_metadata", default=None
)


@contextmanager
def collect_command_metadata() -> Iterator[CommandMetadata]:
    """Collect typed command facts without changing ordinary text execution."""

    metadata = CommandMetadata()
    token = _ACTIVE_METADATA.set(metadata)
    try:
        yield metadata
    finally:
        _ACTIVE_METADATA.reset(token)


def publish_data(**values: object) -> None:
    """Publish public command data when a structured execution is active."""

    metadata = _ACTIVE_METADATA.get()
    if metadata is not None:
        metadata.data.update(values)


def publish_finding(finding: Finding) -> None:
    """Publish one typed finding when a structured execution is active."""

    metadata = _ACTIVE_METADATA.get()
    if metadata is not None:
        metadata.findings.append(finding)


def publish_disclaimer(value: str) -> None:
    metadata = _ACTIVE_METADATA.get()
    if metadata is not None and value not in metadata.disclaimers:
        metadata.disclaimers.append(value)


def _protocol_version_from_project(
    project_root: Path,
    memory_dir: Path,
) -> str | None:
    try:
        manifest_path = memory_dir / "manifest.md"
        if not manifest_path.exists():
            return None
        manifest = read_managed_text(memory_dir, manifest_path)
        metadata = strict_protocol_metadata(manifest)
        version = metadata.get("protocol_version")
        return version if version is not None and parse_version(version) is not None else None
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def project_protocol_version(args) -> str | None:
    """Read the protocol declared by the addressed project, if trustworthy.

    The installed CLI version is never a substitute for project state. A
    missing, malformed, or unparseable manifest deliberately yields ``None``.
    ``init`` supports its historical ``--path`` alias; every other command
    uses ``--memory-dir``.
    """

    try:
        project_root = resolve_project_root(getattr(args, "project_root", "."))
        memory_value = getattr(args, "memory_dir", None)
        if getattr(args, "command", None) == "init":
            alias = getattr(args, "path", None)
            if isinstance(alias, str) and alias:
                memory_value = alias
        memory_dir = resolve_memory_dir(project_root, memory_value)
    except (OSError, TypeError, ValueError):
        return None
    return _protocol_version_from_project(project_root, memory_dir)


def _public_value(
    value: Any,
    *,
    project_root: Path | None,
    memory_dir: Path | None,
) -> Any:
    """Recursively sanitize public string values and stabilize mappings."""

    if isinstance(value, str):
        return sanitize_text(value, project_root=project_root, memory_dir=memory_dir)
    if isinstance(value, Mapping):
        return {
            str(key): _public_value(
                item, project_root=project_root, memory_dir=memory_dir
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _public_value(item, project_root=project_root, memory_dir=memory_dir)
            for item in value
        ]
    return value


def _diagnostic_message(command: str, stderr_text: str, return_code: int) -> str:
    diagnostic = " ".join(line.strip() for line in stderr_text.splitlines() if line.strip())
    if diagnostic:
        return diagnostic
    kind = "a blocker" if return_code == 2 else "a domain failure"
    return f"{command} reported {kind}."


def command_result(
    *,
    command: str,
    protocol_version: str | None,
    handler_return_code: int,
    rendered_text: str,
    stderr_text: str,
    metadata: CommandMetadata,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> CommandResult:
    """Adapt a text handler to the shared result model without stdout parsing.

    The handler code is accepted only as a compatibility assertion. Missing
    failure findings are materialized once here and the final process code is
    then derived from the resulting findings. Any disagreement fails closed
    as an internal contract error instead of emitting contradictory JSON.
    """

    if handler_return_code not in {0, 1, 2}:
        raise ResultContractError(
            f"{command} returned unsupported process status {handler_return_code!r}."
        )
    safe_text = sanitize_text(
        rendered_text, project_root=project_root, memory_dir=memory_dir
    )
    safe_stderr = sanitize_text(
        stderr_text, project_root=project_root, memory_dir=memory_dir
    )
    data = _public_value(
        metadata.data, project_root=project_root, memory_dir=memory_dir
    )
    if command == "read":
        data.setdefault("rendered_context", safe_text)
        data["context_sha256"] = context_sha256(safe_text)

    findings = list(metadata.findings)
    has_error = any(item.severity == "ERROR" for item in findings)
    has_blocker = any(item.severity == "BLOCKER" for item in findings)
    if handler_return_code == 1 and not (has_error or has_blocker):
        findings.append(make_finding(
            "MC-COMMAND-001",
            "ERROR",
            _diagnostic_message(command, safe_stderr, handler_return_code),
            path="docs/memory",
            remediation="Resolve the reported domain failure and retry.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))
    elif handler_return_code == 2 and not has_blocker:
        findings.append(make_finding(
            "MC-COMMAND-002",
            "BLOCKER",
            _diagnostic_message(command, safe_stderr, handler_return_code),
            path="docs/memory",
            remediation="Resolve the reported blocker and retry.",
            project_root=project_root,
            memory_dir=memory_dir,
        ))

    result = CommandResult(
        command=command,
        protocol_version=protocol_version,
        data=data,
        findings=unique_findings(findings),
        rendered_text=safe_text,
        disclaimers=tuple(metadata.disclaimers),
    )
    if result.return_code != handler_return_code:
        raise ResultContractError(
            f"{command} returned {handler_return_code}, but its typed result derives "
            f"{result.return_code} ({result.exit_class})."
        )
    result.validate()
    return result


def domain_failure_result(
    *,
    command: str,
    protocol_version: str | None,
    message: str,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> CommandResult:
    """Build a JSON-domain failure after argument parsing has succeeded."""

    return CommandResult(
        command=command,
        protocol_version=protocol_version,
        findings=(make_finding(
            "MC-INVOCATION-001",
            "ERROR",
            message,
            path="docs/memory",
            remediation="Correct the invocation or project state and retry.",
            project_root=project_root,
            memory_dir=memory_dir,
        ),),
    )


def fatal_failure_result(
    *,
    command: str,
    protocol_version: str | None,
    message: str,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> CommandResult:
    """Build a fatal runtime envelope for an already-selected JSON command."""

    return CommandResult(
        command=command,
        protocol_version=protocol_version,
        findings=(make_finding(
            "MC-RUNTIME-001",
            "BLOCKER",
            message,
            path="private/runtime",
            remediation="Resolve the runtime or environment failure and retry.",
            project_root=project_root,
            memory_dir=memory_dir,
        ),),
        fatal=True,
    )


def public_payload(
    result: CommandResult,
    *,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
    authoritative_protocol: bool = False,
) -> dict[str, object]:
    """Return one sanitized, validated public envelope."""

    result.validate()
    payload = result.payload(output_schema_version=OUTPUT_SCHEMA_VERSION)
    if authoritative_protocol:
        if (
            result.protocol_version is not None
            and parse_version(result.protocol_version) is None
        ):
            payload["protocol_version"] = None
    elif project_root is not None and memory_dir is not None:
        payload["protocol_version"] = _protocol_version_from_project(
            project_root, memory_dir,
        )
    elif result.protocol_version is not None and parse_version(result.protocol_version) is None:
        payload["protocol_version"] = None
    return _public_value(
        payload, project_root=project_root, memory_dir=memory_dir
    )


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
