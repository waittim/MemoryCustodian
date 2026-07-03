"""Check MemoryCustodian protocol consistency."""

from __future__ import annotations

from pathlib import Path

from .protocol import budget_for, count_inbox_items, estimate_tokens, optional_index_paths, resolve_memory_dir, resolve_project_root
from .templates import CORE_FILES


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

    manifest = _read(memory_dir / "manifest.md")
    if manifest:
        issues.extend(_manifest_mentions_required_policy(manifest))

    for path in sorted(memory_dir.rglob("*.md")):
        relative = path.relative_to(memory_dir).as_posix()
        if relative.startswith("archive/"):
            continue
        budget = budget_for(relative)
        if budget is None:
            continue
        tokens = estimate_tokens(_read(path))
        if tokens > budget:
            issues.append(f"{relative}: over budget ({tokens}/{budget} tokens)")

    inbox = memory_dir / "inbox.md"
    if inbox.exists():
        inbox_items = count_inbox_items(_read(inbox))
        if inbox_items > 30:
            warnings.append(f"inbox.md: {inbox_items} items, compaction recommended")

    do_not_use = memory_dir / "do-not-use.md"
    if do_not_use.exists() and "Tombstone:" not in _read(do_not_use):
        warnings.append("do-not-use.md: no tombstones recorded")

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

    for entry_name in ("AGENTS.md", "CLAUDE.md"):
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
