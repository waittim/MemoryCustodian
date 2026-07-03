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

MemoryCustodian uses this file to decide which local project memory files should be loaded for a task.

## MemoryCustodian Protocol
- protocol_version: {protocol_version}
- initialized_with: memory-custodian {package_version}
- last_migrated_with: memory-custodian {package_version}

## Always load
- brief.md

## Load by task

### Planning / architecture / refactoring
Use when the agent is making structural decisions, comparing approaches, writing a plan, or changing project direction.
Load:
- decisions.md
- constraints.md
- do-not-use.md

### Implementation / execution
Use when the agent is writing code, editing files, implementing a plan, debugging, or performing concrete project work.
Load:
- constraints.md
- do-not-use.md
Load if present:
- preferences.md

### User-facing artifact generation
Use when the agent produces text that may be copied, published, submitted, committed, sent, or shown to others.
Load if present:
- rules/output.md
- preferences.md
Also load:
- do-not-use.md

### User or project preferences
Use when the task depends on style, workflow, conventions, or recurring user preferences.
Load if present:
- preferences.md

### Change history / project recap
Use when the user asks what changed, what was decided, or how the project evolved.
Load:
- decisions.md
Load if present:
- changelog.md

### Memory maintenance
Use when adding, compacting, editing, deleting, or auditing memory.
Load:
- inbox.md
- do-not-use.md
Load if present:
- changelog.md

## Optional module index
Agents use this lightweight index to discover optional memory without loading its contents. Entries here are not default loads; load the referenced file only when the trigger applies.

### Enabled rules
- None enabled.

### Enabled profiles
- None enabled.

### Enabled areas
- None enabled.

## Optional rules
Task-specific rules are disabled until a `rules/<name>.md` file exists and is listed in the optional module index.
Load rule files only when the current task clearly matches that rule or the user explicitly requests it.

## Optional profiles
Workflow profiles are disabled until a `profiles/<name>.md` file exists and is listed in the optional module index.
Load profile files only when the current task clearly matches that workflow or the user explicitly requests it.

## Area-specific memory
Area memory is disabled until an `areas/<name>.md` file exists and is listed in the optional module index.
Load area files only when the current task clearly touches that area.

## Explicit only
Do not load these unless the user explicitly asks or the task is memory maintenance:
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
- `AGENTS.md` and `CLAUDE.md` should stay short and only point to this memory folder.

Default behavior:
- Load `manifest.md`.
- Load `brief.md`.
- Load additional memory files only when relevant.
""",
    "decisions.md": """# Decisions

## {date} - Use MemoryCustodian
Decision:
Use MemoryCustodian for repo-native project memory.

Reason:
Project memory should be local, plain-text, inspectable, and reusable across agents.

Implications:
- Keep platform entry files short.
- Store durable context in `{memory_dir}`.
- Avoid RAG or vector DB in MVP.

Status:
active
""",
    "constraints.md": """# Constraints

- Keep AGENTS.md and CLAUDE.md short.
- Store durable project memory in `{memory_dir}`.
- Do not use RAG, embeddings, or vector databases in MVP.
- Do not load archive files unless explicitly requested.
""",
    "do-not-use.md": """# Do Not Use / Tombstones

## Tombstone: Full memory in platform entry files
Status:
Do not use.
Reason:
AGENTS.md and CLAUDE.md should act as thin bootloaders, not full memory stores.
Applies to:
- Platform entry files
- Agent bootstrapping
""",
    "inbox.md": """# Memory Inbox

Unprocessed memory candidates go here.

During compaction:
- Promote stable decisions to `decisions.md`.
- Promote hard limits to `constraints.md`.
- Promote rejected approaches to `do-not-use.md`.
- Update `brief.md` with the shortest useful summary.
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
