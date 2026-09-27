"""Report MemoryCustodian health from the shared structured snapshot."""

from __future__ import annotations

from . import __version__
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    budget_for,
    budget_state,
    compare_versions,
    count_h2_entries,
    count_inbox_items,
    estimate_tokens,
    long_decision_entries,
    resolve_memory_dir,
    resolve_project_root,
)
from .results import CommandResult, make_finding, unique_findings, stable_path
from .snapshot import build_snapshot
from .templates import CORE_FILES, brief_needs_curation


def collect(args) -> CommandResult:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    display_memory = stable_path(memory_dir, project_root=project_root, memory_dir=memory_dir)
    lines = [
        "MemoryCustodian status",
        f"CLI version: {__version__}",
        f"Memory directory: {display_memory}",
    ]
    findings = []
    data: dict[str, object] = {
        "cli_version": __version__,
        "memory_directory": display_memory,
        "files": [],
        "modules": {},
    }
    if not memory_dir.exists():
        lines.append("Status: MISSING")
        findings.append(make_finding(
            "MC-ROUTING-001", "ERROR", "Memory directory is missing.",
            path="docs/memory", project_root=project_root, memory_dir=memory_dir,
        ))
        return CommandResult(
            command="status", protocol_version=None, data=data,
            findings=unique_findings(findings), rendered_text="\n".join(lines) + "\n",
        )

    snapshot = build_snapshot(memory_dir, project_root)
    metadata = snapshot.manifest_contract.as_dict()
    protocol_error = snapshot.manifest_contract.error if snapshot.manifest_contract.present else None
    protocol_version = metadata.get("protocol_version")
    if protocol_error:
        if snapshot.manifest_contract.migration_available:
            line = "Protocol version: 0.7 / entry schema 1 (staged migration available to Entry schema 3)"
            findings.append(make_finding(
                "MC-ROUTING-007", "WARNING", protocol_error,
                path="docs/memory/manifest.md", project_root=project_root, memory_dir=memory_dir,
            ))
        else:
            line = f"Protocol metadata: INVALID ({protocol_error})"
            findings.append(make_finding(
                "MC-ROUTING-007", "ERROR", protocol_error,
                path="docs/memory/manifest.md", project_root=project_root, memory_dir=memory_dir,
            ))
    elif protocol_version:
        comparison = compare_versions(protocol_version, CURRENT_PROTOCOL_VERSION)
        if comparison == 0:
            line = f"Protocol version: {protocol_version} (current)"
        elif comparison is not None and comparison < 0:
            line = f"Protocol version: {protocol_version} (migration available to {CURRENT_PROTOCOL_VERSION})"
            findings.append(make_finding(
                "MC-ROUTING-007", "WARNING", line,
                path="docs/memory/manifest.md", project_root=project_root, memory_dir=memory_dir,
            ))
        elif comparison is not None and comparison > 0:
            line = f"Protocol version: {protocol_version} (newer than CLI supports {CURRENT_PROTOCOL_VERSION})"
            findings.append(make_finding(
                "MC-ROUTING-007", "ERROR", line,
                path="docs/memory/manifest.md", project_root=project_root, memory_dir=memory_dir,
            ))
        else:
            line = f"Protocol version: {protocol_version} (invalid)"
            findings.append(make_finding(
                "MC-ROUTING-007", "ERROR", line,
                path="docs/memory/manifest.md", project_root=project_root, memory_dir=memory_dir,
            ))
    else:
        line = f"Protocol version: missing (migration available to {CURRENT_PROTOCOL_VERSION})"
        findings.append(make_finding(
            "MC-ROUTING-001", "ERROR", "manifest.md is missing protocol metadata.",
            path="docs/memory/manifest.md", project_root=project_root, memory_dir=memory_dir,
        ))
    lines.append(line)
    data["protocol"] = {"version": protocol_version, "current": CURRENT_PROTOCOL_VERSION}

    files_by_relative = {item.relative: item for item in snapshot.files}
    for name in CORE_FILES:
        source = files_by_relative.get(name)
        if source is None:
            lines.append(f"{name}: MISSING")
            findings.append(make_finding(
                "MC-ROUTING-005", "ERROR", f"{name}: missing required core file.",
                path=name, project_root=project_root, memory_dir=memory_dir,
            ))
            continue
        text = source.text
        tokens = estimate_tokens(text)
        budget = budget_for(name)
        usage_state = budget_state(tokens, budget) if budget is not None else "OK"
        long_entries = long_decision_entries(text) if name == "decisions.md" else []
        if name == "manifest.md" and protocol_error:
            state = "INVALID"
        elif name == "brief.md" and brief_needs_curation(text):
            state = "NEEDS CURATION"
        elif usage_state != "OK":
            state = usage_state
        elif long_entries:
            state = "LONG ENTRIES"
        else:
            state = "OK"
        detail = f", {tokens} tokens"
        if budget is not None:
            detail += f"/{budget} max"
        if state == "OVER BUDGET":
            detail += f", run compact --target {name}"
        elif state == "NEAR LIMIT":
            detail += f", maintenance recommended before next write; run compact --target {name}"
        elif state == "NEEDS CURATION":
            detail += ", replace generated placeholders with real project context"
        elif state == "LONG ENTRIES":
            detail += f", shorten {len(long_entries)} decision(s) over {DECISION_ENTRY_BUDGET} tokens"
        if name == "inbox.md":
            count = count_inbox_items(text)
            detail += f", {count} items"
            if count > 30:
                detail += ", compaction recommended"
        if name in {"decisions.md", "do-not-use.md"}:
            detail += f", {count_h2_entries(text)} entries"
        lines.append(f"{name}: {state}{detail}")
        data["files"].append({"path": name, "status": state, "tokens": tokens, "budget": budget})
        if state != "OK":
            severity = "ERROR" if state in {"OVER BUDGET", "LONG ENTRIES", "INVALID", "NEEDS CURATION"} else "WARNING"
            code = "MC-BUDGET-001" if state in {"OVER BUDGET", "NEAR LIMIT"} else "MC-ENTRY-002"
            findings.append(make_finding(
                code, severity, f"{name}: {state}.", path=name,
                remediation="Review the status detail and apply the recommended maintenance action.",
                project_root=project_root, memory_dir=memory_dir,
            ))

    for name in ("preferences.md", "changelog.md"):
        source = files_by_relative.get(name)
        if source is None:
            lines.append(f"{name}: not enabled")
            data["files"].append({"path": name, "status": "not enabled"})
            continue
        text = source.text
        tokens = estimate_tokens(text)
        budget = budget_for(name)
        state = "OK" if budget is None else budget_state(tokens, budget)
        detail = f", {tokens} tokens"
        if budget is not None:
            detail += f"/{budget} max"
        if state in {"NEAR LIMIT", "OVER BUDGET"}:
            detail += f", run compact --target {name}"
            findings.append(make_finding(
                "MC-BUDGET-001", "ERROR" if state == "OVER BUDGET" else "WARNING",
                f"{name}: {state}.", path=name,
                project_root=project_root, memory_dir=memory_dir,
            ))
        lines.append(f"{name}: {state}{detail}")
        data["files"].append({"path": name, "status": state, "tokens": tokens, "budget": budget})

    for folder in ("rules", "profiles", "areas", "archive"):
        folder_files = [item for item in snapshot.files if item.relative.startswith(folder + "/")]
        enabled = snapshot.memory_dir / folder in snapshot.managed_directories or bool(folder_files)
        if not enabled:
            state = "not enabled"
            lines.append(f"{folder}/: {state}")
            data["modules"][folder] = {"status": state, "files": []}
            continue
        files = sorted(
            item.relative.removeprefix(folder + "/")
            for item in folder_files
            if item.relative.count("/") == 1
        )
        state = "enabled" + (f", {len(files)} markdown file(s)" if files else ", empty")
        lines.append(f"{folder}/: {state}")
        data["modules"][folder] = {"status": state, "files": files}

    result = CommandResult(
        command="status",
        protocol_version=protocol_version,
        data=data,
        findings=unique_findings(findings),
        rendered_text="\n".join(lines) + "\n",
    )
    return result


def run(args) -> int:
    result = collect(args)
    print(result.rendered_text, end="")
    return result.return_code
