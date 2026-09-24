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
from .mutations import PrivateTextMutation, TextMutation
from .mutations import _validate_write_target
from .output import PUBLIC_PLAN_SCHEMA_VERSION, publish_data, publish_finding
from .results import make_finding


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_path(path: Path) -> str:
    """Return an existence-aware digest of the file's original bytes.

    ``missing`` is deliberately distinct from the SHA-256 of an empty file.
    Plan IDs therefore cannot silently treat a newly-created empty file as an
    unchanged missing operand, and newline/encoding normalization never
    participates in the stale-plan check.
    """

    exists, data = _read_regular_bytes(path)
    return hashlib.sha256(data).hexdigest() if exists else "missing"


def _read_regular_bytes(path: Path) -> tuple[bool, bytes]:
    candidate = path.expanduser().absolute()
    _validate_write_target(candidate)
    try:
        before = candidate.lstat()
    except FileNotFoundError:
        return False, b""
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Plan operand must be a regular non-symlink file: {path}")
    try:
        descriptor = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError(f"Plan operand could not be opened safely: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            before.st_dev, before.st_ino
        ) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"Plan operand changed during safe open: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return True, b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_regular_text(path: Path) -> str:
    exists, data = _read_regular_bytes(path)
    if not exists:
        raise FileNotFoundError(path)
    return data.decode("utf-8")


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
    path = _find_pending_operation(
        command, project_root, source_sha256, tuple(sorted(keys)), "entry_suffixes"
    )
    if path is None:
        path = pending_plan_directory() / f"{command}-{uuid.uuid4().hex}.json"
        generated = {item: uuid.uuid4().hex[:8] for item in keys}
        payload = json.dumps(
            {
                "command": command,
                "project_root_key": _project_root_key(project_root),
                "source_sha256": source_sha256,
                "keys": sorted(keys),
                "entry_suffixes": generated,
            },
            sort_keys=True,
        ) + "\n"
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

    path = _find_pending_operation(command, project_root, source_sha256, (), "plan_nonce")
    if path is None:
        path = pending_plan_directory() / f"{command}-{uuid.uuid4().hex}.json"
        generated = uuid.uuid4().hex
        payload = json.dumps(
            {
                "command": command,
                "project_root_key": _project_root_key(project_root),
                "source_sha256": source_sha256,
                "plan_nonce": generated,
            },
            sort_keys=True,
        ) + "\n"
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


def _project_root_key(project_root: Path) -> str:
    return hashlib.sha256(
        str(project_root.expanduser().resolve()).encode("utf-8")
    ).hexdigest()


def _find_pending_operation(
    command: str,
    project_root: Path,
    source_sha256: str,
    keys: tuple[str, ...],
    value_key: str,
) -> Path | None:
    """Find a private pending operation without selector-derived filenames."""

    directory = pending_plan_directory()
    root_key = _project_root_key(project_root)
    for path in sorted(directory.glob(f"{command}-*.json")):
        try:
            payload = json.loads(read_private_file(path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("command") != command:
            continue
        if payload.get("project_root_key") != root_key:
            continue
        if payload.get("source_sha256") != source_sha256:
            continue
        if tuple(payload.get("keys", ())) != keys:
            continue
        if value_key not in payload:
            continue
        return path
    return None


def pending_plan_digest(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        value = json.loads(read_private_file(path)).get("private_plan_id")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def record_pending_plan_digest(path: Path | None, private_plan_id: str) -> None:
    if path is None:
        return
    if not re.fullmatch(r"[0-9a-f]{64}", private_plan_id):
        raise ValueError("Private plan digest is malformed.")
    payload = json.loads(read_private_file(path))
    if not isinstance(payload, dict):
        raise ValueError("Pending plan state is malformed.")
    payload["private_plan_id"] = private_plan_id
    from .locking import write_private_file

    write_private_file(path, json.dumps(payload, sort_keys=True) + "\n")


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
    private_mutations: tuple[PrivateTextMutation, ...] = ()
    dependency_paths: tuple[Path, ...] = ()
    # Repo-external read-only inputs use ``(stable_alias, path)`` pairs so
    # machine-absolute local-overlay paths never enter the private digest.
    # A bare Path is accepted for compatibility and uses its normalized path
    # only in the private (never public) canonical form.
    private_dependency_paths: tuple[Path | tuple[str, Path], ...] = ()

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
                "operation": "replace" if digest_path(mutation.path) != "missing" else "create",
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

    def _private_operations(self, *, include_digests: bool) -> list[dict[str, object]]:
        """Render private overlay mutations without exposing their real paths."""

        operations: list[dict[str, object]] = []
        for mutation in sorted(self.private_mutations, key=lambda item: item.relative):
            relative = mutation.relative.replace("\\", "/")
            operation: dict[str, object] = {
                "path": f"local/{relative}",
                "operation": "replace" if digest_path(mutation.path) != "missing" else "create",
            }
            if include_digests:
                operation["base_sha256"] = digest_path(mutation.path)
                # The private writer preserves the supplied bytes; unlike the
                # shared write_text helper it does not add a terminal newline.
                operation["expected_output_sha256"] = digest_text(mutation.text)
            operations.append(operation)
        return operations

    def private_canonical(self) -> dict[str, object]:
        operations = [
            *self._operations(include_digests=True),
            *self._private_operations(include_digests=True),
        ]
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
            "dependency_snapshots": self._dependency_snapshots(),
            "private_dependency_snapshots": self._private_dependency_snapshots(),
            "budget_results": self._budget_results(),
        }

    def _dependency_snapshots(self) -> list[dict[str, str]]:
        snapshots = []
        for path in sorted(self.dependency_paths, key=lambda item: self._canonical_path(item)):
            snapshots.append({
                "path": self._canonical_path(path),
                "digest": digest_path(path),
            })
        return snapshots

    def _private_dependency_snapshots(self) -> list[dict[str, str]]:
        snapshots: list[dict[str, str]] = []
        for item in self.private_dependency_paths:
            if isinstance(item, tuple):
                if len(item) != 2 or not isinstance(item[0], str) or not isinstance(item[1], Path):
                    raise ValueError("Private dependency must be a (stable alias, Path) pair.")
                alias, path = item
            elif isinstance(item, Path):
                # Preserve compatibility with callers that supplied a bare
                # path before explicit aliases were available.  The absolute
                # path is reduced to an opaque stable label so separators or
                # machine-specific roots can never leak into a rendered plan.
                path = item
                location = os.path.normcase(str(path.expanduser().absolute())).encode("utf-8")
                alias = "path-" + hashlib.sha256(location).hexdigest()[:32]
            else:
                raise ValueError("Private dependency must be a Path or (stable alias, Path) pair.")
            if not alias or "/" in alias or "\\" in alias or alias in {".", ".."}:
                raise ValueError("Private dependency alias is invalid.")
            snapshots.append({"alias": alias, "digest": digest_path(path)})
        return sorted(snapshots, key=lambda item: item["alias"])

    @property
    def private_plan_id(self) -> str:
        """Recompute the private stale-check digest on every access."""

        encoded = json.dumps(
            self.private_canonical(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _opaque_reference(self) -> str:
        private_context = self.private_context or {}
        for key in ("operation_reference", "privacy_nonce"):
            value = private_context.get(key)
            if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{16,64}", value):
                return value[:16]
        raise ValueError("Sensitive plan is missing its opaque pending operation reference.")

    def canonical(self) -> dict[str, object]:
        operations = [
            *self._operations(
                include_digests=not self.sensitive,
                public=True,
            ),
            *self._private_operations(
                include_digests=not self.sensitive,
            ),
        ]
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
        if self.sensitive:
            return self._opaque_reference()
        return self.private_plan_id[:16]


def publish_plan(plan: MutationPlan) -> dict[str, object]:
    """Publish the bounded public view of an internal execution plan."""

    canonical = plan.canonical()
    public = {
        "public_plan_schema_version": PUBLIC_PLAN_SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "readiness": "blocked" if canonical["blockers"] else "ready",
        "targets": [
            {
                key: value
                for key, value in operation.items()
                if key in {
                    "path", "operation", "base_sha256", "expected_output_sha256",
                    "digests",
                }
            }
            for operation in canonical["operations"]
        ],
        "blockers": list(canonical["blockers"]),
        "warnings": list(canonical["warnings"]),
        "budget_results": list(canonical["budget_results"]),
    }
    publish_data(plan=public)
    for warning in canonical["warnings"]:
        publish_finding(make_finding(
            "MC-PLAN-002",
            "WARNING",
            str(warning),
            path="docs/memory",
            remediation="Review the preview warning before applying the plan.",
        ))
    return public


def print_plan(plan: MutationPlan) -> None:
    public = publish_plan(plan)
    print(f"Plan ID: {public['plan_id']}")
    print("Target files:")
    for operation in public["targets"]:
        print(f"- {operation['path']}")
        print(f"  Operation: {operation['operation']}")
        if "base_sha256" in operation:
            print(f"  Base SHA-256: {operation['base_sha256']}")
            print(f"  Expected SHA-256: {operation['expected_output_sha256']}")
        else:
            print("  Digests: redacted for sensitive operation")
    print("Blockers:")
    for blocker in public["blockers"]:
        print(f"- {blocker}")
    if not public["blockers"]:
        print("- none")
    print("Warnings:")
    for warning in public["warnings"]:
        print(f"- {warning}")
    if not public["warnings"]:
        print("- none")
    print("Estimated budget result:")
    if public["budget_results"]:
        for result in public["budget_results"]:
            print(
                f"- {result['path']}: {result['before']} -> {result['after']} tokens "
                f"(limit {result['limit']}, state {result['state']})"
            )
    else:
        print("- unchanged or not applicable")
