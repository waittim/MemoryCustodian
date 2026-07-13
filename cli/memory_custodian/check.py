"""Check MemoryCustodian protocol consistency."""

from __future__ import annotations

from pathlib import Path
import re

from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    DECISION_ENTRY_BUDGET,
    budget_for,
    compare_versions,
    count_inbox_items,
    estimate_tokens,
    long_decision_entries,
    optional_index_paths,
    protocol_metadata,
    resolve_memory_dir,
    resolve_project_root,
)
from .templates import CORE_FILES, brief_needs_curation


LOCAL_PATH_RE = re.compile(r"(?:/Users/|/home/|/Volumes/|[A-Za-z]:[\\/])")


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
    metadata = protocol_metadata(text)
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
    issues: list[str] = []
    warnings: list[str] = []

    if not memory_dir.exists():
        print(f"Memory directory missing: {memory_dir}")
        return 1

    for name in CORE_FILES:
        if not (memory_dir / name).exists():
            issues.append(f"{name}: missing required core file")

    manifest_path = memory_dir / "manifest.md"
    manifest = _read(manifest_path)
    if manifest_path.exists():
        issues.extend(_check_protocol_metadata(manifest))
    if manifest:
        issues.extend(_manifest_mentions_required_policy(manifest))

    brief = _read(memory_dir / "brief.md")
    if brief and brief_needs_curation(brief):
        issues.append("brief.md: generated scaffold still needs real project purpose, direction, and system context")

    for path in sorted(memory_dir.rglob("*.md")):
        relative = path.relative_to(memory_dir).as_posix()
        if relative.startswith("archive/"):
            continue
        budget = budget_for(relative)
        if budget is None:
            continue
        tokens = estimate_tokens(_read(path))
        if tokens > budget:
            issues.append(f"{relative}: over budget ({tokens}/{budget} tokens); run `memory-custodian compact --target {relative}`")
        for title, entry_tokens in long_decision_entries(_read(path)):
            issues.append(
                f"{relative}: decision {title!r} is too long ({entry_tokens}/{DECISION_ENTRY_BUDGET} tokens); "
                "shorten it semantically and move supporting detail outside the decision entry"
            )

    inbox = memory_dir / "inbox.md"
    if inbox.exists():
        inbox_items = count_inbox_items(_read(inbox))
        if inbox_items > 30:
            warnings.append(f"inbox.md: {inbox_items} items, compaction recommended")

    preferences = memory_dir / "preferences.md"
    if preferences.exists() and LOCAL_PATH_RE.search(_read(preferences)):
        warnings.append(
            "preferences.md: contains a machine-specific absolute path; confirm it belongs in shared project memory"
        )

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

    return 1 if issues else 0
