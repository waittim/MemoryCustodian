"""Stable public output envelopes for Protocol 0.8 commands."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .results import CommandResult, Finding, make_finding, sanitize_text, stable_path


OUTPUT_SCHEMA_VERSION = 1
PUBLIC_PLAN_SCHEMA_VERSION = 1


def _section_items(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = lines.index(heading + ":") + 1
    except ValueError:
        return []
    values: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith(("- ", "  ")):
            break
        if line.startswith("- "):
            value = line[2:].strip()
            if value not in {"none", "none supplied"}:
                values.append(value)
    return values


def _read_contract_data(text: str) -> dict[str, object]:
    scalar_labels = {
        "Task": "supplied_task",
        "Canonical task": "canonical_task",
        "Routing completeness": "routing_completeness",
        "Local overlay status": "local_overlay_status",
        "Conflict status": "conflict_status",
    }
    data: dict[str, object] = {}
    for line in text.splitlines():
        for label, key in scalar_labels.items():
            if line.startswith(label + ":"):
                data[key] = line.split(":", 1)[1].strip()
    data["normalized_paths"] = _section_items(text, "Paths")
    data["explicit_modules"] = _section_items(text, "Explicit scope")
    data["loaded_modules"] = _section_items(text, "Loaded")
    data["skipped_modules"] = _section_items(text, "Skipped optional")
    data["missing_required_modules"] = _section_items(text, "Missing required")
    data["missing_optional_modules"] = _section_items(text, "Missing optional")
    data["invalid_modules"] = _section_items(text, "Invalid")
    data["budget_omissions"] = _section_items(text, "Budget omissions")
    data["warnings"] = _section_items(text, "Warnings")
    data["conflict_findings"] = []
    data["reconciliation_findings"] = []
    data["loaded_entry_ids"] = sorted(set(re.findall(
        r"(?m)^##\s+(MC-(?:DEC|CON|DNU|PREF|AREA|TOMB)-\d{8}-[0-9a-f]{8})\b",
        text,
        re.I,
    )), key=str.casefold)
    data["subject_ids"] = sorted(set(re.findall(
        r"(?m)^Subject:\s*(MC-SUBJ-\d{8}-[0-9a-f]{8})\s*$", text, re.I,
    )), key=str.casefold)
    data["facets"] = sorted(set(re.findall(
        r"(?m)^Facet:\s*([^\s]+)\s*$", text,
    )), key=str.casefold)
    dispositions: list[dict[str, object]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("- "):
            continue
        module = line[2:].strip()
        if not module.endswith(".md") and not module.endswith("/"):
            continue
        record: dict[str, object] = {"module": module}
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].startswith("  "):
            child = lines[cursor].strip()
            if ":" in child:
                key, value = child.split(":", 1)
                record[key.casefold().replace(" ", "_")] = value.strip()
            cursor += 1
        if len(record) > 1:
            dispositions.append(record)
    data["module_dispositions"] = dispositions
    data["rendered_context"] = text
    return data


def _public_plan(
    text: str,
    *,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> dict[str, object] | None:
    match = re.search(r"(?m)^Plan ID:\s*([A-Za-z0-9._-]+)\s*$", text)
    if match is None:
        return None
    targets: list[dict[str, object]] = []
    lines = text.splitlines()
    in_targets = False
    for index, line in enumerate(lines):
        if line == "Target files:":
            in_targets = True
            continue
        if not in_targets:
            continue
        if line and not line.startswith(("- ", "  ")):
            break
        if line.startswith("- "):
            target: dict[str, object] = {
                "path": stable_path(
                    line[2:].strip(),
                    project_root=project_root,
                    memory_dir=memory_dir,
                )
            }
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].startswith("  "):
                child = lines[cursor].strip()
                if ":" in child:
                    key, value = child.split(":", 1)
                    normalized = key.casefold().replace(" ", "_").replace("-", "_")
                    target[normalized] = sanitize_text(
                        value.strip(),
                        project_root=project_root,
                        memory_dir=memory_dir,
                    )
                cursor += 1
            targets.append(target)
    return {
        "public_plan_schema_version": PUBLIC_PLAN_SCHEMA_VERSION,
        "plan_id": match.group(1),
        "targets": targets,
    }


def _erasure_scope(text: str) -> dict[str, object] | None:
    labels = {
        "Schema": "erasure_scope_schema_version",
        "Operation phase": "operation_phase",
        "Active managed memory": "active_memory",
        "Managed archive": "managed_archive",
        "New tombstones/logs retain topic": "topic_retained_in_new_records",
        "Local overlay": "local_overlay",
        "Git worktree modified": "git_worktree_modified",
        "Git history modified": "git_history_modified",
        "Existing clones, forks and backups revoked": "distributed_copies_revoked",
        "History inspection": "history_check_status",
    }
    values: dict[str, object] = {}
    for line in text.splitlines():
        match = re.match(r"^- ([^:]+):\s*(.*)$", line)
        if not match or match.group(1) not in labels:
            continue
        value: object = match.group(2)
        if value in {"yes", "no"}:
            value = value == "yes"
        elif labels[match.group(1)] == "erasure_scope_schema_version":
            try:
                value = int(str(value))
            except ValueError:
                continue
        values[labels[match.group(1)]] = value
    return values if "erasure_scope_schema_version" in values else None


def envelope(
    *,
    command: str,
    protocol_version: str | None,
    return_code: int,
    rendered_text: str,
    data: dict[str, object] | None = None,
    findings: list[dict[str, object]] | None = None,
    disclaimers: list[str] | None = None,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> dict[str, object]:
    # Keep this compatibility helper for callers that still provide a plain
    # dict, but route status/exit mapping through the shared result model.
    parsed_findings = tuple(
        Finding(
            code=str(item.get("code", "MC-OUTPUT-001")),
            severity=str(item.get("severity", "ERROR")),
            path=stable_path(item.get("path", ""), project_root=project_root, memory_dir=memory_dir),
            entry_id=item.get("entry_id"),
            message=sanitize_text(str(item.get("message", "")), project_root=project_root, memory_dir=memory_dir),
            remediation=sanitize_text(str(item.get("remediation", "")), project_root=project_root, memory_dir=memory_dir),
            details=item.get("details", {}) if isinstance(item.get("details", {}), dict) else {},
        )
        for item in findings or []
    )
    payload_data = dict(data or {})
    safe_text = sanitize_text(
        rendered_text,
        project_root=project_root,
        memory_dir=memory_dir,
    )
    payload_data.setdefault("rendered_text", safe_text)
    if command == "read":
        payload_data.update(_read_contract_data(safe_text))
        normalized = safe_text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized and not normalized.endswith("\n"):
            normalized += "\n"
        payload_data["context_sha256"] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    plan = _public_plan(safe_text, project_root=project_root, memory_dir=memory_dir)
    if plan is not None:
        payload_data["plan"] = plan
    erasure = _erasure_scope(safe_text)
    if erasure is not None:
        payload_data["erasure_scope"] = erasure
    result = CommandResult(
        command=command,
        protocol_version=protocol_version,
        data=payload_data,
        findings=parsed_findings,
        rendered_text=safe_text,
        disclaimers=tuple(disclaimers or ()),
        explicit_return_code=return_code,
    )
    return result.payload(output_schema_version=OUTPUT_SCHEMA_VERSION)


def structured_command_data(
    command: str,
    text: str,
    *,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
    args=None,
) -> dict[str, object]:
    """Build stable command data for legacy text-only command implementations.

    New read-only commands use ``CommandResult`` directly.  Mutation/preview
    commands still have intentionally small text renderers; this adapter
    extracts only documented fields and never serializes a private
    ``MutationPlan`` or an absolute path.
    """

    safe = sanitize_text(text, project_root=project_root, memory_dir=memory_dir)
    data: dict[str, object] = {}
    lines = safe.splitlines()
    if command == "list":
        entries: list[dict[str, str]] = []
        for line in lines:
            match = re.match(r"^-\s+(\S+)\s+\[([^;]+);\s*([^\]]+)\]\s+(.+)$", line)
            if match:
                entries.append({
                    "entry_id": match.group(1),
                    "status": match.group(2),
                    "scope": match.group(3),
                    "source": stable_path(match.group(4), project_root=project_root, memory_dir=memory_dir),
                })
        data["entries"] = sorted(entries, key=lambda item: (item["entry_id"].casefold(), item["source"]))
    elif command == "show":
        source = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Source:")), "")
        data["source"] = stable_path(source, project_root=project_root, memory_dir=memory_dir)
        data["entry"] = {"text": safe}
    elif command == "recover":
        transactions: list[dict[str, object]] = []
        current: dict[str, object] | None = None
        for line in lines:
            if line.startswith("- ") and not line.startswith("- Issue:"):
                if current:
                    transactions.append(current)
                current = {"transaction_id": line[2:].strip()}
            elif current is not None and line.strip().startswith(("Phase:", "Operation:", "Complete safe:", "Rollback safe:")):
                key, value = line.strip().split(":", 1)
                normalized = key.casefold().replace(" ", "_")
                current[normalized] = value.strip().lower() in {"yes", "true"} if normalized.endswith("safe") else value.strip()
        if current:
            transactions.append(current)
        data["transactions"] = transactions
        data["recovery_status"] = "clean" if "Transactions: clean" in safe else "recovery-required"
    elif command == "status":
        data["memory_directory"] = next(
            (line.split(":", 1)[1].strip() for line in lines if line.startswith("Memory directory:")),
            "docs/memory",
        )
        data["files"] = [
            {"path": line.split(":", 1)[0], "status": line.split(":", 1)[1].split(",", 1)[0].strip()}
            for line in lines
            if ": " in line and line.split(":", 1)[0].endswith((".md", "/"))
        ]
    elif command == "check":
        data["check_status"] = "FAILED" if "check: FAILED" in safe else "OK"
    # Read, plans, erasure, and all other command-specific fields are added by
    # ``envelope`` itself.  Keep the text as an explicit compatibility view.
    return data


def structured_findings(
    command: str,
    text: str,
    *,
    project_root: Path | None = None,
    memory_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Extract only documented domain diagnostics for legacy text commands.

    This compatibility parser is intentionally limited to the mutation and
    recovery renderers.  ``audit``, ``check`` and ``status`` never use it;
    those commands construct the shared result model at source.
    """

    findings: list[dict[str, object]] = []
    section: str | None = None
    for line in sanitize_text(text, project_root=project_root, memory_dir=memory_dir).splitlines():
        stripped = line.strip()
        if stripped in {"Warnings:", "Blockers:"}:
            section = stripped[:-1].casefold()
            continue
        if stripped in {"Estimated budget result:", "Target files:", "Findings:"}:
            continue
        severity = None
        message = ""
        code = "MC-OUTPUT-001"
        if stripped.startswith("Warning:"):
            severity, message, code = "WARNING", stripped.split(":", 1)[1].strip(), "MC-OUTPUT-002"
        elif stripped.startswith("Error:"):
            severity, message, code = "ERROR", stripped.split(":", 1)[1].strip(), "MC-INVOCATION-001"
        elif stripped.startswith("Manual rewrite required") or stripped.startswith("Refusing "):
            severity, message, code = "ERROR", stripped, "MC-PLAN-001"
        elif stripped.startswith("- ") and section in {"warnings", "blockers"}:
            severity = "WARNING" if section == "warnings" else "ERROR"
            message = stripped[2:].strip()
            code = "MC-PLAN-002" if severity == "WARNING" else "MC-PLAN-001"
        if severity:
            findings.append(make_finding(
                code, severity, message, path="docs/memory",
                project_root=project_root, memory_dir=memory_dir,
            ).canonical())
    return findings


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
