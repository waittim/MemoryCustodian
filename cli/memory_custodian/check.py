"""Check MemoryCustodian protocol consistency."""

from __future__ import annotations

from pathlib import Path
import re

from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    budget_for,
    budget_state,
    compare_versions,
    count_inbox_items,
    estimate_tokens,
    long_decision_entries,
    parse_markdown_units,
    parse_manifest_task_file_specs,
    read_no_follow_text,
    protocol_contract_metadata,
    resolve_manifest_memory_path,
    resolve_memory_dir,
    resolve_project_root,
)
from .entries import (
    heading_entry_ids,
)
from .scanning import scan_text
from .integrity import cross_unit_integrity_findings
from .templates import CORE_FILES, brief_needs_curation
from .conflicts import (
    ConflictStatus,
    analyze_snapshot,
    render_conflict_result,
)
from .quality import (
    freshness_findings,
    reachability_findings,
    render_quality,
    routing_findings,
)
from .local_overlay import (
    LocalStatus,
    inspect_overlay,
)
from .snapshot import build_snapshot


def _read(path: Path) -> str:
    return read_no_follow_text(path, required=False) if path.exists() else ""


def _check_agent_entry(path: Path) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return issues
    text = _read(path)
    tokens = estimate_tokens(text)
    if tokens > 500:
        issues.append(f"{path.name}: may be too long for a thin entry file ({tokens} tokens)")
    copied_sections = sum(1 for marker in ("# Decisions", "# Constraints", "# Do Not Use", "# Memory Inbox") if marker in text)
    if copied_sections:
        issues.append(f"{path.name}: appears to copy memory content instead of pointing to docs/memory")
    if path.name == "GEMINI.md" and any(marker in text for marker in ("@./docs/memory/", "@/docs/memory/", "@docs/memory/")):
        issues.append("GEMINI.md: should not import docs/memory files; point to the manifest instead")
    return issues


def _manifest_mentions_required_policy(text: str) -> list[str]:
    issues: list[str] = []
    required_terms = {
        "brief.md": "brief.md",
        "do-not-use.md": "do-not-use.md",
        "archive/": "archive/",
        "rules/": "rules/",
        "profiles/": "profiles/",
    }
    for label, term in required_terms.items():
        if term not in text:
            issues.append(f"manifest.md: missing policy mention for {label}")
    return issues


def _check_protocol_metadata(
    text: str,
    *,
    contract=None,
) -> list[str]:
    issues: list[str] = []
    if contract is not None:
        if not contract.present:
            return [
                "manifest.md: invalid protocol metadata "
                "[MC-ROUTING-007 INVALID]: manifest.md is missing."
            ]
        if contract.error is not None:
            if (
                not contract.as_dict()
                and contract.error.startswith("Invalid manifest routing:")
                and "MemoryCustodian Protocol" not in text
            ):
                return [
                    "manifest.md: missing MemoryCustodian Protocol metadata "
                    f"[MC-ROUTING-007 INVALID]: {contract.error}"
                ]
            return [
                "manifest.md: invalid protocol metadata "
                f"[MC-ROUTING-007 INVALID]: {contract.error}"
            ]
        metadata = contract.as_dict()
        if not metadata:
            return [
                "manifest.md: missing MemoryCustodian Protocol metadata; "
                "run `memory-custodian migrate --apply`"
            ]
        version = metadata.get("protocol_version")
        if not version:
            return [
                "manifest.md: missing protocol_version; "
                "run `memory-custodian migrate --apply`"
            ]
        comparison = compare_versions(version, CURRENT_PROTOCOL_VERSION)
        if comparison is None:
            issues.append(f"manifest.md: invalid protocol_version {version!r}")
        elif comparison < 0:
            issues.append(
                f"manifest.md: protocol_version {version} is older than current {CURRENT_PROTOCOL_VERSION}; "
                "run `memory-custodian migrate --apply`"
            )
        elif comparison > 0:
            issues.append(
                f"manifest.md: protocol_version {version} is newer than this CLI supports ({CURRENT_PROTOCOL_VERSION}); "
                "update memory-custodian"
            )
        return issues
    try:
        metadata = protocol_contract_metadata(text, allow_missing_section=True)
    except ValueError as exc:
        return [f"manifest.md: invalid protocol metadata: {exc}"]
    if not metadata:
        return ["manifest.md: missing MemoryCustodian Protocol metadata; run `memory-custodian migrate --apply`"]
    version = metadata.get("protocol_version")
    if not version:
        return ["manifest.md: missing protocol_version; run `memory-custodian migrate --apply`"]
    comparison = compare_versions(version, CURRENT_PROTOCOL_VERSION)
    if comparison is None:
        issues.append(f"manifest.md: invalid protocol_version {version!r}")
    elif comparison < 0:
        issues.append(
            f"manifest.md: protocol_version {version} is older than current {CURRENT_PROTOCOL_VERSION}; "
            "run `memory-custodian migrate --apply`"
        )
    elif comparison > 0:
        issues.append(
            f"manifest.md: protocol_version {version} is newer than this CLI supports ({CURRENT_PROTOCOL_VERSION}); "
            "update memory-custodian"
        )
    return issues


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory missing: {memory_dir}")
        return 1
    # Capture every shared managed-memory input once.  All focused checks and
    # the ordinary diagnostics below consume this immutable view; in
    # particular, no preflight may reread manifest.md before this boundary.
    snapshot = build_snapshot(memory_dir, project_root)
    if getattr(args, "conflicts", False):
        if not snapshot.manifest_contract.valid:
            print("Conflict status: INVALID")
            print(
                "MC-ROUTING-007 INVALID: "
                f"{snapshot.manifest_contract.error or 'manifest.md is missing.'}"
            )
            return 1
        result = analyze_snapshot(snapshot)
        render_conflict_result(result)
        if getattr(args, "merge_base", None):
            from .merge_review import merge_review
            merge_result = merge_review(project_root, memory_dir, args.merge_base)
            print(merge_result.text)
            if merge_result.blocking:
                return 1
        return 1 if result.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID} else 0
    if getattr(args, "routing", False):
        return render_quality(
            "routing check",
            routing_findings(memory_dir, snapshot=snapshot),
        )
    if getattr(args, "reachability", False):
        return render_quality(
            "reachability check",
            reachability_findings(memory_dir, snapshot=snapshot),
        )
    if getattr(args, "freshness", False):
        return render_quality(
            "freshness check",
            freshness_findings(project_root, memory_dir, snapshot=snapshot),
        )
    issues: list[str] = []
    warnings: list[str] = []
    detailed_findings = []

    files_by_relative = {item.relative: item for item in snapshot.files}
    for name in CORE_FILES:
        if name not in files_by_relative:
            issues.append(f"{name}: missing required core file")

    manifest = snapshot.manifest_text
    issues.extend(
        _check_protocol_metadata(
            manifest,
            contract=snapshot.manifest_contract,
        )
    )
    if manifest:
        issues.extend(_manifest_mentions_required_policy(manifest))
        for task in ("default", "planning", "implementation", "artifact", "preferences", "history", "maintenance"):
            try:
                specs = parse_manifest_task_file_specs(manifest, task)
            except ValueError:
                continue
            for name, required in specs:
                try:
                    path = resolve_manifest_memory_path(memory_dir, name)
                except ValueError as exc:
                    issue = f"manifest.md: {exc}"
                    if issue not in issues:
                        issues.append(issue)
                    continue
                relative = path.relative_to(memory_dir).as_posix()
                if required and relative not in files_by_relative:
                    issue = f"manifest.md: required route file is missing: {name}"
                    if issue not in issues:
                        issues.append(issue)

    brief = files_by_relative.get("brief.md").text if "brief.md" in files_by_relative else ""
    if brief and brief_needs_curation(brief):
        issues.append("brief.md: generated scaffold still needs real project purpose, direction, and system context")

    for item in snapshot.files:
        relative = item.relative
        text = item.text
        issues.extend(item.check_issues)
        warnings.extend(item.check_warnings)
        detailed_findings.extend(scan_text(item.path, text))
        if item.archive:
            continue
        if relative in {
            "decisions.md", "constraints.md", "do-not-use.md", "preferences.md", "inbox.md"
        } or relative.startswith(("areas/", "rules/", "profiles/")):
            units = parse_markdown_units(text).units
            legacy_h2 = sum(
                1
                for unit in units
                if unit.kind == "h2"
                and not (unit.heading and re.search(
                    r"\bMC-(?:DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-\d{8}-[0-9a-f]{8}\b",
                    unit.heading,
                    re.I,
                ))
            )
            legacy_bullets = sum(1 for unit in units if unit.kind == "bullet")
            legacy_count = legacy_h2 + legacy_bullets
            if legacy_count:
                warnings.append(
                    f"{relative}: {legacy_count} legacy entr{'y' if legacy_count == 1 else 'ies'} "
                    "remain readable without structured Evidence"
                )

        ids = heading_entry_ids(text)
        if len({value.casefold() for value in ids}) != len(ids):
            issues.append(f"{relative}: duplicate Entry ID within file")
        budget = budget_for(relative)
        if budget is None:
            continue
        tokens = estimate_tokens(text)
        state = budget_state(tokens, budget)
        if state == "OVER BUDGET":
            issues.append(f"{relative}: over budget ({tokens}/{budget} tokens); run `memory-custodian compact --target {relative}`")
        elif state == "NEAR LIMIT":
            warnings.append(
                f"{relative}: near limit ({tokens}/{budget} tokens); maintenance recommended before "
                f"the next write; run `memory-custodian compact --target {relative}`"
            )
        for title, entry_tokens in long_decision_entries(text):
            issues.append(
                f"{relative}: decision {title!r} is too long ({entry_tokens}/{DECISION_ENTRY_BUDGET} tokens); "
                "shorten it semantically and move supporting detail outside the decision entry"
            )

    metadata = snapshot.manifest_contract.as_dict()
    overlay_project_id = (
        metadata.get("project_id")
        if snapshot.manifest_contract.valid
        and compare_versions(
            metadata.get("protocol_version", "0.5"),
            CURRENT_PROTOCOL_VERSION,
        ) == 0
        else None
    )
    overlay = (
        inspect_overlay(
            project_root,
            overlay_project_id,
            shared_ids={entry.entry_id for entry in snapshot.relation_entries},
        )
        if overlay_project_id is not None
        else None
    )
    local_paths: set[Path] = set()
    if (
        overlay is not None
        and overlay.directory is not None
        and overlay.status in {LocalStatus.BOUND, LocalStatus.REVIEW}
    ):
        for captured in overlay.captured_modules:
            path = captured.path
            local_paths.add(path)
            text = captured.text
            detailed_findings.extend(scan_text(path, text))
            for entry in captured.entries:
                if entry.scope not in {"local-user", "local-machine"}:
                    issues.append(
                        f"local/{path.relative_to(overlay.directory).as_posix()}: "
                        f"{entry.entry_id} has non-local Scope {entry.scope!r}"
                    )

    inbox_file = files_by_relative.get("inbox.md")
    if inbox_file is not None:
        inbox_items = count_inbox_items(inbox_file.text)
        if inbox_items > 30:
            warnings.append(f"inbox.md: {inbox_items} items, compaction recommended")

    cross_issues, cross_warnings = cross_unit_integrity_findings(
        project_root,
        memory_dir,
        manifest,
        project_id=overlay_project_id,
        snapshot=snapshot,
        overlay=overlay,
    )
    issues.extend(cross_issues)
    warnings.extend(cross_warnings)

    for entry_name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        warnings.extend(_check_agent_entry(project_root / entry_name))

    all_ids: dict[str, list[str]] = {}
    for item in snapshot.files:
        if item.path.name.casefold() == "readme.md":
            continue
        for value in heading_entry_ids(item.text):
            all_ids.setdefault(value.casefold(), []).append(item.relative)
    for value, paths in all_ids.items():
        if len(paths) > 1:
            issues.append(f"duplicate Entry ID {value.upper()} in: {', '.join(paths)}")

    security = [item for item in detailed_findings if item.category == "security"]
    privacy = [item for item in detailed_findings if item.category == "privacy"]
    security_errors = [item for item in security if item.severity == "ERROR"]
    security_warnings = [item for item in security if item.severity != "ERROR"]
    def finding_location(finding) -> str:
        if finding.path in local_paths:
            return f"local/{finding.path.relative_to(overlay.directory).as_posix()}"
        return finding.path.relative_to(memory_dir).as_posix()

    if getattr(args, "security", False):
        for finding in security:
            message = f"{finding_location(finding)}:{finding.line}: {finding.kind}: {finding.preview}"
            (issues if finding.severity == "ERROR" else warnings).append(message)
    else:
        if security_errors:
            issues.append(
                f"security scan: {len(security_errors)} error finding(s); "
                "run `memory-custodian check --security` for redacted locations"
            )
        if security_warnings:
            warnings.append(
                f"security scan: {len(security_warnings)} warning finding(s); "
                "run `memory-custodian check --security` for redacted locations"
            )
    if getattr(args, "privacy", False):
        for finding in privacy:
            warnings.append(
                f"{finding_location(finding)}:{finding.line}: {finding.kind}: {finding.preview}"
            )
    elif privacy:
        if any(
            item.kind == "machine-path"
            and finding_location(item) == "preferences.md"
            for item in privacy
        ):
            warnings.append(
                "preferences.md: contains a machine-specific absolute path; "
                "run `memory-custodian check --privacy` for redacted locations"
            )
        warnings.append(
            f"privacy scan: {len(privacy)} finding(s); "
            "run `memory-custodian check --privacy` for redacted locations"
        )

    if issues:
        print("MemoryCustodian check: FAILED")
        for issue in issues:
            print(f"- {issue}")
    else:
        print("MemoryCustodian check: OK")

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    if getattr(args, "security", False):
        print(f"Security findings: {len(security)}")
    if getattr(args, "privacy", False):
        print(f"Privacy findings: {len(privacy)}")

    return 1 if issues else 0
