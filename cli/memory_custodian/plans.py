"""Canonical mutation plans and confirmation identifiers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .locking import (
    create_private_file,
    discard_private_file,
    discard_expired_private_files,
    private_state_directory,
    read_private_file,
)
from .mutations import TextMutation


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_path(path: Path) -> str:
    return (
        digest_text(_read_regular_text(path))
        if path.exists() or path.is_symlink()
        else digest_text("")
    )


def _read_regular_text(path: Path) -> str:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Plan operand must be a regular non-symlink file: {path}")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError(f"Plan operand could not be opened safely: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            before.st_dev, before.st_ino
        ) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"Plan operand changed during safe open: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


PENDING_PLAN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def pending_plan_directory() -> Path:
    directory = private_state_directory("plans")
    discard_expired_private_files(
        directory,
        max_age_seconds=PENDING_PLAN_MAX_AGE_SECONDS,
        suffixes=(".json", ".id"),
    )
    return directory


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
    path = pending_plan_directory() / f"{command}-{key}.json"
    generated = str(uuid.uuid4())
    payload = json.dumps({"project_id": generated}, sort_keys=True) + "\n"
    create_private_file(path, payload)
    try:
        value = json.loads(read_private_file(path)).get("project_id")
        parsed = uuid.UUID(str(value))
        if parsed.version != 4:
            raise ValueError
        return str(parsed), path
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid pending plan seed: {path}") from exc


def pending_entry_suffixes(
    command: str,
    project_root: Path,
    source_sha256: str,
    keys: list[str],
) -> tuple[dict[str, str], Path | None]:
    """Create or reuse UUIDv4-derived suffixes for a preview/apply migration pair."""

    if not keys:
        return {}, None
    key = pending_seed_key(command, project_root, source_sha256)
    path = pending_plan_directory() / f"{command}-{key}.json"
    generated = {item: uuid.uuid4().hex[:8] for item in keys}
    payload = json.dumps({"entry_suffixes": generated}, sort_keys=True) + "\n"
    create_private_file(path, payload)
    try:
        values = json.loads(read_private_file(path)).get("entry_suffixes")
        if not isinstance(values, dict):
            raise ValueError
        result = {}
        for item in keys:
            value = values.get(item)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}", value):
                raise ValueError
            result[item] = value
        return result, path
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid pending entry ID seed: {path}") from exc


def pending_plan_nonce(
    command: str,
    project_root: Path,
    source_sha256: str,
) -> tuple[str, Path]:
    """Create or reuse a full-width random nonce for a sensitive private plan."""

    key = pending_seed_key(command, project_root, source_sha256)
    path = pending_plan_directory() / f"{command}-{key}.json"
    generated = uuid.uuid4().hex
    payload = json.dumps({"plan_nonce": generated}, sort_keys=True) + "\n"
    create_private_file(path, payload)
    try:
        value = json.loads(read_private_file(path)).get("plan_nonce")
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ValueError
        return value, path
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid pending private plan nonce: {path}") from exc


def discard_pending_seed(path: Path | None) -> None:
    discard_private_file(path)


@dataclass(frozen=True)
class MutationPlan:
    command: str
    arguments: dict[str, object]
    project_id: str
    protocol_version: str
    mutations: tuple[TextMutation, ...]
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    context: dict[str, object] | None = None
    budget_results: tuple[dict[str, object], ...] = ()
    project_root: Path | None = None
    public_arguments: dict[str, object] | None = None
    private_context: dict[str, object] | None = None
    sensitive: bool = False
    public_redactions: tuple[str, ...] = ()

    def _canonical_path(self, path: Path) -> str:
        if self.project_root is None:
            return path.as_posix()
        root = self.project_root.resolve()
        resolved = path.resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"Mutation target must be inside the project root: {path}"
            ) from exc

    def _public_string(self, value: str) -> str:
        redacted = value
        for secret in self.public_redactions:
            if secret:
                redacted = re.sub(
                    re.escape(secret),
                    "[redacted]",
                    redacted,
                    flags=re.IGNORECASE,
                )
        return redacted

    def _json_value(self, value, *, public: bool = False):
        if isinstance(value, Path):
            canonical = self._canonical_path(value)
            return self._public_string(canonical) if public else canonical
        if isinstance(value, dict):
            return {
                str(key): self._json_value(item, public=public)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [self._json_value(item, public=public) for item in value]
        if public and isinstance(value, str):
            return self._public_string(value)
        return value

    def _budget_results(self) -> list[dict[str, object]]:
        if self.budget_results:
            return list(self.budget_results)
        from .protocol import budget_for, budget_state, estimate_tokens

        results: list[dict[str, object]] = []
        for mutation in self.mutations:
            parent = mutation.path.parent.name
            name = (
                f"{parent}/{mutation.path.name}"
                if parent in {"rules", "profiles", "areas"}
                else mutation.path.name
            )
            limit = budget_for(name)
            if limit is None:
                continue
            before_text = (
                _read_regular_text(mutation.path)
                if mutation.path.exists() or mutation.path.is_symlink()
                else ""
            )
            before = estimate_tokens(before_text)
            after = estimate_tokens(mutation.text)
            results.append(
                {
                    "path": name,
                    "before": before,
                    "after": after,
                    "limit": limit,
                    "state": budget_state(after, limit),
                }
            )
        return results

    def _operations(
        self,
        *,
        include_digests: bool,
        public: bool = False,
    ) -> list[dict[str, object]]:
        operations = []
        for mutation in sorted(
            self.mutations,
            key=lambda item: self._canonical_path(item.path),
        ):
            canonical_path = self._canonical_path(mutation.path)
            operation: dict[str, object] = {
                "path": (
                    self._public_string(canonical_path)
                    if public
                    else canonical_path
                ),
                "operation": "replace" if mutation.path.exists() else "create",
            }
            if include_digests:
                operation["base_sha256"] = digest_path(mutation.path)
                operation["expected_output_sha256"] = digest_text(
                    mutation.text
                    if mutation.text.endswith("\n")
                    else mutation.text + "\n"
                )
            operations.append(operation)
        return operations

    def private_canonical(self) -> dict[str, object]:
        operations = self._operations(include_digests=True)
        return {
            "command": self.command,
            "arguments": self._json_value(self.arguments),
            "project_id": self.project_id,
            "protocol_version": self.protocol_version,
            "target_paths": [item["path"] for item in operations],
            "operations": operations,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "context": self._json_value(self.context or {}),
            "private_context": self._json_value(self.private_context or {}),
            "budget_results": self._budget_results(),
        }

    def canonical(self) -> dict[str, object]:
        operations = self._operations(
            include_digests=not self.sensitive,
            public=True,
        )
        return {
            "command": self.command,
            "arguments": self._json_value(
                self.public_arguments
                if self.public_arguments is not None
                else self.arguments,
                public=True,
            ),
            "project_id": self.project_id,
            "protocol_version": self.protocol_version,
            "target_paths": [item["path"] for item in operations],
            "operations": operations,
            "warnings": self._json_value(self.warnings, public=True),
            "blockers": self._json_value(self.blockers, public=True),
            "context": self._json_value(self.context or {}, public=True),
            "budget_results": self._json_value(
                self._budget_results(),
                public=True,
            ),
        }

    @property
    def plan_id(self) -> str:
        encoded = json.dumps(
            self.private_canonical(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]


def print_plan(plan: MutationPlan) -> None:
    canonical = plan.canonical()
    print(f"Plan ID: {plan.plan_id}")
    print("Target files:")
    for operation in canonical["operations"]:
        print(f"- {operation['path']}")
        print(f"  Operation: {operation['operation']}")
        if "base_sha256" in operation:
            print(f"  Base SHA-256: {operation['base_sha256']}")
            print(f"  Expected SHA-256: {operation['expected_output_sha256']}")
        else:
            print("  Digests: redacted for sensitive operation")
    print("Blockers:")
    for blocker in canonical["blockers"]:
        print(f"- {blocker}")
    if not canonical["blockers"]:
        print("- none")
    print("Warnings:")
    for warning in canonical["warnings"]:
        print(f"- {warning}")
    if not canonical["warnings"]:
        print("- none")
    print("Estimated budget result:")
    if canonical["budget_results"]:
        for result in canonical["budget_results"]:
            print(
                f"- {result['path']}: {result['before']} -> {result['after']} tokens "
                f"(limit {result['limit']}, state {result['state']})"
            )
    else:
        print("- unchanged or not applicable")
