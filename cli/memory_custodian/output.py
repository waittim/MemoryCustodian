"""Stable public output envelopes for Protocol 0.8 commands."""

from __future__ import annotations

import hashlib
import json
import re


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


def _public_plan(text: str) -> dict[str, object] | None:
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
            target: dict[str, object] = {"path": line[2:].strip()}
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].startswith("  "):
                child = lines[cursor].strip()
                if ":" in child:
                    key, value = child.split(":", 1)
                    normalized = key.casefold().replace(" ", "_").replace("-", "_")
                    target[normalized] = value.strip()
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
) -> dict[str, object]:
    findings = findings or []
    has_blocker = any(item.get("severity") == "BLOCKER" for item in findings)
    has_error = any(item.get("severity") == "ERROR" for item in findings)
    has_warning = any(item.get("severity") == "WARNING" for item in findings)
    if return_code or has_error or has_blocker:
        status = "FAIL"
        exit_class = "blocker" if return_code == 2 or has_blocker else "domain-failure"
    elif has_warning or "Warnings:" in rendered_text and "- none" not in rendered_text:
        status = "REVIEW"
        exit_class = "success-with-review"
    else:
        status = "PASS"
        exit_class = "success"
    payload_data = dict(data or {})
    payload_data.setdefault("rendered_text", rendered_text)
    if command == "read":
        payload_data.update(_read_contract_data(rendered_text))
        normalized = rendered_text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized and not normalized.endswith("\n"):
            normalized += "\n"
        payload_data["context_sha256"] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    plan = _public_plan(rendered_text)
    if plan is not None:
        payload_data["plan"] = plan
    erasure = _erasure_scope(rendered_text)
    if erasure is not None:
        payload_data["erasure_scope"] = erasure
    return {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "command": command,
        "protocol_version": protocol_version,
        "status": status,
        "exit_class": exit_class,
        "data": payload_data,
        "findings": findings,
        "disclaimers": disclaimers or [],
    }


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
