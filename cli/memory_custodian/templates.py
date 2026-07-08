"""Built-in project memory templates."""

from __future__ import annotations

from . import __protocol_version__, __version__

DEFAULT_MEMORY_DIR = "docs/memory"

CORE_FILES = (
    "manifest.md",
    "brief.md",
    "decisions.md",
    "constraints.md",
    "do-not-use.md",
    "inbox.md",
)

OPTIONAL_FILES = (
    "preferences.md",
    "changelog.md",
    "rules/README.md",
    "profiles/README.md",
    "archive/README.md",
)

MEMORY_FILES = {
    "manifest.md": """# Memory Manifest

Loading map for local project memory. Load only the files listed for the current task plus explicitly requested optional modules.

## MemoryCustodian Protocol
- protocol_version: {protocol_version}
- initialized_with: memory-custodian {package_version}
- last_migrated_with: memory-custodian {package_version}

## Always load
- brief.md

## Load by task

### Planning / architecture / refactoring
Load:
- decisions.md
- constraints.md
- do-not-use.md

### Implementation / execution / debugging
Load:
- constraints.md
- do-not-use.md
Load if present:
- preferences.md

### User-facing artifact / output
Load:
- do-not-use.md
Load if present:
- rules/output.md
- preferences.md

### Preferences
Load if present:
- preferences.md

### Change history / recap
Load:
- decisions.md
Load if present:
- changelog.md

### Memory maintenance
Load:
- inbox.md
- do-not-use.md
Load if present:
- changelog.md

## Optional module index
Discover optional memory without loading it. Entries here are not default loads.

### Enabled rules
- None enabled.

### Enabled profiles
- None enabled.

### Enabled areas
- None enabled.

## Optional rules
`rules/` files load only when listed above and the task clearly matches.

## Optional profiles
`profiles/` files load only when listed above and the workflow clearly matches.

## Area-specific memory
`areas/` files load only when listed above and the touched files or task scope match.

## Explicit only
- archive/

## Context budget
- brief.md: 500 tokens max
- decisions.md: 800 tokens max
- constraints.md: 400 tokens max
- do-not-use.md: 400 tokens max
- preferences.md: 300 tokens max, if present
- rules/*.md: 400 tokens max per file, if present
- profiles/*.md: 500 tokens max per file, if present
- areas/*.md: 600 tokens max per file, if present
- changelog.md: 800 tokens max, if present
- inbox.md: memory maintenance only
- archive/: explicit only
""",
    "brief.md": """# Project Brief

This project uses MemoryCustodian to maintain local, plain-text project memory.

Current status:
- Minimal memory protocol is enabled.
- Durable memory lives in `{memory_dir}`.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` should stay short and only point to this memory folder.

Default behavior:
- Load `manifest.md`.
- Load `brief.md`.
- Load additional memory files only when relevant.
""",
    "decisions.md": """# Decisions

Entries are newest first.

## {date} - Use MemoryCustodian
Decision:
Use local Markdown files under `{memory_dir}` for durable project memory. Keep platform entry files short bootstraps.

Reason:
Memory should be inspectable, diffable, portable, and reusable across agents.

Implications:
- Load context through `manifest.md`.
- Avoid RAG or vector DB in MVP.
""",
    "constraints.md": """# Constraints

- Keep AGENTS.md, CLAUDE.md, and GEMINI.md short.
- Store durable project memory in `{memory_dir}`.
- Do not use RAG, embeddings, or vector databases in MVP.
- Do not load archive files unless explicitly requested.
""",
    "do-not-use.md": """# Do Not Use / Tombstones

Tombstones are newest first.

## Tombstone: Full memory in platform entry files
Do not copy full memory into AGENTS.md, CLAUDE.md, GEMINI.md, or similar files. They should stay thin bootstraps that point to `{memory_dir}`.
""",
    "inbox.md": """# Memory Inbox

Entries are newest first.

No unprocessed memory candidates.
""",
    "preferences.md": """# Preferences

Soft user or project preferences go here. Hard requirements belong in `constraints.md`.
""",
    "changelog.md": """# Memory Changelog

Entries are newest first.

## {date}
- Enabled MemoryCustodian changelog.
""",
    "rules/README.md": """# Memory Rules

Task-specific rules go here. Create one file per rule type, such as:
- `output.md`
- `code-style.md`
- `safety.md`
- `review.md`

Load a rule file only when the current task clearly matches it.
""",
    "profiles/README.md": """# Memory Profiles

Workflow-specific profiles go here. Create one file per workflow, such as:
- `git.md`
- `docs.md`
- `release.md`
- `tickets.md`
- `research.md`

Load a profile file only when the current task clearly matches it.
""",
    "archive/README.md": """# Memory Archive

Old or raw memory material may be archived here.

Do not load archive files unless the user explicitly asks or the task is memory maintenance.
""",
}

EXPECTED_FILES = CORE_FILES
ALL_TEMPLATE_FILES = CORE_FILES + OPTIONAL_FILES


def render_template(name: str, date: str, memory_dir: str = DEFAULT_MEMORY_DIR) -> str:
    return (
        MEMORY_FILES[name]
        .format(date=date, memory_dir=memory_dir, package_version=__version__, protocol_version=__protocol_version__)
        .rstrip()
        + "\n"
    )


def render_rule_template(name: str, date: str) -> str:
    title = name.replace("-", " ").replace("_", " ").title()
    return (
        f"# Rule: {title}\n\n"
        "Use this file for task-specific rules. Keep it short and operational.\n\n"
        "## Rules\n"
        "- Add rules that should apply only when this task type is relevant.\n"
    )


def render_profile_template(name: str, date: str) -> str:
    title = name.replace("-", " ").replace("_", " ").title()
    return (
        f"# Profile: {title}\n\n"
        "Use this file for workflow-specific memory. Keep workflow rules separate from core project memory.\n\n"
        "## Rules\n"
        "- Add workflow rules that should apply only when this profile is relevant.\n"
    )


def render_area_template(name: str, date: str) -> str:
    title = name.replace("-", " ").replace("_", " ").title()
    return (
        f"# Area: {title}\n\n"
        "Use this file for area-specific memory in a large repo or monorepo.\n\n"
        "## Context\n"
        "- Add durable context that should load only when this area is touched.\n"
    )
