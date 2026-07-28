"""Canonical mutation plans and confirmation identifiers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from .locking import state_root
from .mutations import TextMutation


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_path(path: Path) -> str:
    return digest_text(path.read_text(encoding="utf-8")) if path.exists() else digest_text("")


def _writable_plan_dir() -> Path:
    primary = state_root() / "plans"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        probe = primary / f".write-probe-{os.getpid()}-{uuid.uuid4().hex}"
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        probe.unlink()
        return primary
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "memory-custodian-state" / "plans"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def pending_seed_key(command: str, project_root: Path, manifest_sha256: str) -> str:
    payload = json.dumps(
        {
            "command": command,
            "project_root": str(project_root.resolve()),
            "manifest_sha256": manifest_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def pending_project_id(command: str, project_root: Path, manifest_sha256: str) -> tuple[str, Path]:
    """Create or reuse a random UUIDv4 seed for a preview/apply pair."""

    key = pending_seed_key(command, project_root, manifest_sha256)
    path = _writable_plan_dir() / f"{command}-{key}.json"
    generated = str(uuid.uuid4())
    payload = json.dumps({"project_id": generated}, sort_keys=True) + "\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        descriptor = None
    if descriptor is not None:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("project_id")
        parsed = uuid.UUID(str(value))
        if parsed.version != 4:
            raise ValueError
        return str(parsed), path
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid pending plan seed: {path}") from exc


def discard_pending_seed(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


@dataclass(frozen=True)
class MutationPlan:
    command: str
    arguments: dict[str, object]
    project_id: str
    protocol_version: str
    mutations: tuple[TextMutation, ...]
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def canonical(self) -> dict[str, object]:
        operations = []
        for mutation in sorted(self.mutations, key=lambda item: str(item.path)):
            operations.append(
                {
                    "path": str(mutation.path),
                    "base_sha256": digest_path(mutation.path),
                    "operation": "replace" if mutation.path.exists() else "create",
                    "expected_output_sha256": digest_text(mutation.text if mutation.text.endswith("\n") else mutation.text + "\n"),
                }
            )
        return {
            "command": self.command,
            "arguments": self.arguments,
            "project_id": self.project_id,
            "protocol_version": self.protocol_version,
            "target_paths": [item["path"] for item in operations],
            "operations": operations,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }

    @property
    def plan_id(self) -> str:
        encoded = json.dumps(self.canonical(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]


def print_plan(plan: MutationPlan) -> None:
    canonical = plan.canonical()
    print(f"Plan ID: {plan.plan_id}")
    print("Target files:")
    for operation in canonical["operations"]:
        print(f"- {operation['path']}")
        print(f"  Base SHA-256: {operation['base_sha256']}")
        print(f"  Operation: {operation['operation']}")
        print(f"  Expected SHA-256: {operation['expected_output_sha256']}")
    print("Blockers:")
    for blocker in plan.blockers:
        print(f"- {blocker}")
    if not plan.blockers:
        print("- none")
    print("Warnings:")
    for warning in plan.warnings:
        print(f"- {warning}")
    if not plan.warnings:
        print("- none")
    print("Estimated budget result: command-specific output above, or unchanged/not applicable.")
