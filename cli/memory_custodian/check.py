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
    manifest_contract_metadata,
    optional_index_paths,
    parse_markdown_units,
    parse_manifest_task_file_specs,
    protocol_contract_metadata,
    protocol_metadata,
    resolve_manifest_memory_path,
    resolve_memory_dir,
    resolve_project_root,
    validate_manifest_routes,
)
from .entries import (
    CANDIDATE_ONLY_EVIDENCE,
    INTERNAL_EVIDENCE,
    VALID_SCOPES_RE,
    heading_entry_ids,
    memory_entry_ids,
    parse_structured_entries,
    structured_entry_schema_issues,
    structured_entry_storage_issues,
    structured_relation_issues,
    validate_evidence,
)
from .scanning import scan_text
from .subjects import FACETS, load_subjects, subject_indexes, validate_subject_registry
from .templates import CORE_FILES, brief_needs_curation
from .conflicts import ConflictStatus, analyze_conflicts, render_conflict_result
from .quality import (
    QualityFinding,
    freshness_findings,
    reachability_findings,
    render_quality,
    routing_findings,
)
from .local_overlay import (
    LocalStatus,
    inspect_overlay,
    read_local_private_file,
    validated_project_identity,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


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


def _check_protocol_metadata(text: str) -> list[str]:
    issues: list[str] = []
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


def _specialized_protocol_finding(memory_dir: Path) -> QualityFinding | None:
    manifest_path = memory_dir / "manifest.md"
    if not manifest_path.exists():
        return QualityFinding("ERROR", "MC-ROUTING-007", "manifest.md is missing.")
    try:
        manifest_contract_metadata(
            manifest_path.read_text(encoding="utf-8"),
            allow_missing_section=True,
        )
    except ValueError as exc:
        return QualityFinding("ERROR", "MC-ROUTING-007", str(exc))
    return None


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory directory missing: {memory_dir}")
        return 1
    if getattr(args, "conflicts", False):
        specialized_protocol = _specialized_protocol_finding(memory_dir)
        if specialized_protocol:
            print("Conflict status: INVALID")
            print(
                f"{specialized_protocol.code} {specialized_protocol.severity}: "
                f"{specialized_protocol.message}"
            )
            return 1
        result = analyze_conflicts(memory_dir)
        render_conflict_result(result)
        if getattr(args, "merge_base", None):
            from .merge_review import merge_review
            merge_result = merge_review(project_root, memory_dir, args.merge_base)
            print(merge_result.text)
            if merge_result.blocking:
                return 1
        return 1 if result.status in {ConflictStatus.CONFLICT, ConflictStatus.INVALID} else 0
    if getattr(args, "routing", False):
        return render_quality("routing check", routing_findings(memory_dir))
    if getattr(args, "reachability", False):
        return render_quality("reachability check", reachability_findings(memory_dir))
    if getattr(args, "freshness", False):
        return render_quality("freshness check", freshness_findings(project_root, memory_dir))
    issues: list[str] = []
    warnings: list[str] = []
    detailed_findings = []
    structured_by_id: dict[str, list] = {}
    active_identities: dict[tuple[str, str, str], tuple[str, str]] = {}

    for name in CORE_FILES:
        if not (memory_dir / name).exists():
            issues.append(f"{name}: missing required core file")

    manifest_path = memory_dir / "manifest.md"
    manifest = _read(manifest_path)
    if manifest_path.exists():
        issues.extend(_check_protocol_metadata(manifest))
        if protocol_metadata(manifest).get("subject_schema_version") == "1":
            issues.extend(validate_subject_registry(memory_dir, project_root))
    if manifest:
        issues.extend(_manifest_mentions_required_policy(manifest))
        issues.extend(f"manifest.md: {issue}" for issue in validate_manifest_routes(manifest))
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
                if required and not path.exists():
                    issue = f"manifest.md: required route file is missing: {name}"
                    if issue not in issues:
                        issues.append(issue)

    subjects = load_subjects(memory_dir)
    subjects_by_id, _subjects_by_alias, _subjects_by_ref = subject_indexes(subjects)

    brief = _read(memory_dir / "brief.md")
    if brief and brief_needs_curation(brief):
        issues.append("brief.md: generated scaffold still needs real project purpose, direction, and system context")

    for path in sorted(memory_dir.rglob("*.md")):
        relative = path.relative_to(memory_dir).as_posix()
        text = _read(path)
        detailed_findings.extend(scan_text(path, text))
        parsed_entries = parse_structured_entries(path, text)
        for entry in parsed_entries:
            structured_by_id.setdefault(entry.entry_id.casefold(), []).append(entry)
            issues.extend(structured_entry_schema_issues(entry, relative))
            issues.extend(structured_entry_storage_issues(entry, relative))
        if relative.startswith("archive/"):
            continue
        for entry in parsed_entries:
            expected_inbox = relative == "inbox.md"
            if entry.status not in {"active", "candidate", "superseded", "promoted"}:
                issues.append(f"{relative}: {entry.entry_id} has invalid Status {entry.status!r}")
            if entry.status == "candidate" and not expected_inbox:
                issues.append(f"{relative}: candidate {entry.entry_id} must be stored in inbox.md")
            if expected_inbox and entry.status not in {"candidate", "promoted"}:
                issues.append(
                    f"{relative}: {entry.entry_id} has Status {entry.status!r}; "
                    "inbox entries must be candidate or promoted"
                )
            if entry.status == "promoted" and not entry.fields.get("Promoted-To"):
                issues.append(f"{relative}: promoted entry {entry.entry_id} has no Promoted-To")
            if entry.status == "superseded" and not entry.fields.get("Superseded-By"):
                issues.append(f"{relative}: superseded entry {entry.entry_id} has no Superseded-By")
            if entry.status == "active":
                if not entry.evidence:
                    issues.append(f"{relative}: active entry {entry.entry_id} has no Evidence")
                elif all(item in CANDIDATE_ONLY_EVIDENCE for item in entry.evidence):
                    issues.append(f"{relative}: active entry {entry.entry_id} has only unconfirmed Evidence")
                if "legacy-unverified" in entry.evidence:
                    warnings.append(f"{relative}: {entry.entry_id} uses migration-only legacy-unverified Evidence")
            if entry.status in {"active", "candidate", "superseded", "promoted"}:
                candidate_entry = entry.status in {"candidate", "promoted"}
                if entry.evidence:
                    try:
                        validate_evidence(
                            entry.evidence,
                            project_root,
                            candidate=candidate_entry,
                            allow_missing=True,
                            allow_internal=not candidate_entry,
                        )
                    except ValueError:
                        issues.append(
                            f"{relative}: {entry.entry_id} has invalid Evidence schema "
                            "or unsafe source path"
                        )
                elif candidate_entry:
                    issues.append(
                        f"{relative}: {entry.entry_id} has no Evidence"
                    )
            if not VALID_SCOPES_RE.fullmatch(entry.scope):
                issues.append(f"{relative}: {entry.entry_id} has invalid Scope {entry.scope!r}")
            code = entry.entry_id.split("-", 2)[1].upper()
            managed_subject_type = code in {"DEC", "CON", "DNU", "AREA"}
            subject_id = entry.fields.get("Subject", "")
            facet = entry.fields.get("Facet", "")
            if entry.status == "active" and managed_subject_type:
                if not subject_id or not facet:
                    warnings.append(
                        f"{relative}: {entry.entry_id} legacy Subject/Facet coverage is incomplete"
                    )
                else:
                    subject = subjects_by_id.get(subject_id.casefold())
                    if subject is None:
                        issues.append(
                            f"{relative}: {entry.entry_id} references missing or inactive Subject {subject_id}"
                        )
                    if facet not in FACETS:
                        issues.append(
                            f"{relative}: {entry.entry_id} has invalid Facet {facet!r}"
                        )
                    identity = (entry.scope.casefold(), subject_id.casefold(), facet.casefold())
                    owner = active_identities.get(identity)
                    if owner:
                        issues.append(
                            f"{relative}: {entry.entry_id} duplicates active structural owner "
                            f"{owner[0]} in {owner[1]} for Scope+Subject+Facet"
                        )
                    else:
                        active_identities[identity] = (entry.entry_id, relative)
            if entry.status in {"candidate", "promoted"}:
                provisional_subject = entry.fields.get("Provisional-Subject", "")
                provisional_facet = entry.fields.get("Provisional-Facet", "")
                if bool(provisional_subject) != bool(provisional_facet):
                    issues.append(
                        f"{relative}: {entry.entry_id} must declare Provisional-Subject and "
                        "Provisional-Facet together"
                    )
                elif provisional_subject:
                    if provisional_subject.casefold() not in subjects_by_id:
                        issues.append(
                            f"{relative}: {entry.entry_id} references missing or inactive "
                            f"Provisional-Subject {provisional_subject}"
                        )
                    if provisional_facet not in FACETS:
                        issues.append(
                            f"{relative}: {entry.entry_id} has invalid "
                            f"Provisional-Facet {provisional_facet!r}"
                        )
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
        for title, entry_tokens in long_decision_entries(_read(path)):
            issues.append(
                f"{relative}: decision {title!r} is too long ({entry_tokens}/{DECISION_ENTRY_BUDGET} tokens); "
                "shorten it semantically and move supporting detail outside the decision entry"
            )

    try:
        overlay_project_id = validated_project_identity(memory_dir)
    except (OSError, ValueError):
        overlay_project_id = None
    overlay = (
        inspect_overlay(
            project_root,
            overlay_project_id,
            shared_ids=memory_entry_ids(memory_dir),
        )
        if overlay_project_id is not None
        else None
    )
    local_paths: set[Path] = set()
    if overlay is not None and overlay.status == LocalStatus.REVIEW:
        target = issues if overlay.corrupt else warnings
        target.extend(f"local overlay: {warning}" for warning in overlay.warnings)
    if (
        overlay is not None
        and overlay.directory is not None
        and overlay.status in {LocalStatus.BOUND, LocalStatus.REVIEW}
    ):
        for path in overlay.modules:
            local_paths.add(path)
            text = read_local_private_file(path)
            detailed_findings.extend(scan_text(path, text))
            for entry in parse_structured_entries(path, text):
                if entry.scope not in {"local-user", "local-machine"}:
                    issues.append(
                        f"local/{path.relative_to(overlay.directory).as_posix()}: "
                        f"{entry.entry_id} has non-local Scope {entry.scope!r}"
                    )

    inbox = memory_dir / "inbox.md"
    if inbox.exists():
        inbox_items = count_inbox_items(_read(inbox))
        if inbox_items > 30:
            warnings.append(f"inbox.md: {inbox_items} items, compaction recommended")

    indexed_optional_paths = optional_index_paths(manifest)
    for folder in ("rules", "profiles", "areas"):
        directory = memory_dir / folder
        if not directory.exists():
            continue
        if folder + "/" not in manifest:
            issues.append(f"manifest.md: {folder}/ exists but manifest does not describe when to load it")
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            relative = path.relative_to(memory_dir).as_posix()
            if relative not in indexed_optional_paths:
                issues.append(f"manifest.md: {relative} exists but is missing from optional module index")

    for entry_name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        warnings.extend(_check_agent_entry(project_root / entry_name))

    all_ids: dict[str, list[str]] = {}
    for path in sorted(memory_dir.rglob("*.md")):
        for value in heading_entry_ids(_read(path)):
            all_ids.setdefault(value.casefold(), []).append(path.relative_to(memory_dir).as_posix())
    for value, paths in all_ids.items():
        if len(paths) > 1:
            issues.append(f"duplicate Entry ID {value.upper()} in: {', '.join(paths)}")

    issues.extend(structured_relation_issues([
        entry
        for matches in structured_by_id.values()
        for entry in matches
    ]))

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
