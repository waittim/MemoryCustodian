"""Canonical mutation plans and confirmation identifiers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .mutations import TextMutation


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_path(path: Path) -> str:
    return digest_text(path.read_text(encoding="utf-8")) if path.exists() else digest_text("")


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
