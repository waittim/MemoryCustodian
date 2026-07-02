# Manifest Policy

`manifest.md` is the routing layer for MemoryCustodian. It tells an agent which memory files may enter context for a task.

## Responsibilities

- Define the default memory files.
- Map task types to additional files.
- Identify optional rules, profiles, and areas.
- Mark `archive/` as explicit-only.
- State context budgets.

The manifest should not contain full project memory, decision history, or long rules. Put durable content in the relevant memory file and keep the manifest short.

## Default Loading

Always load:

- `brief.md`

Do not load these by default:

- `inbox.md`
- `archive/`
- unrelated `rules/*.md`
- unrelated `profiles/*.md`
- unrelated `areas/*.md`

## Task Routing

Use these task categories unless the project manifest says otherwise:

- Planning / architecture / refactoring: `decisions.md`, `constraints.md`, `do-not-use.md`
- Implementation / execution: `constraints.md`, `do-not-use.md`, and `preferences.md` if present
- User-facing artifact generation: `do-not-use.md`, `rules/output.md` if present, and `preferences.md` if present
- Preferences: `preferences.md` if present
- Recap / history: `decisions.md` and `changelog.md` if present
- Memory maintenance: `inbox.md`, `do-not-use.md`, and `changelog.md` if present

## Optional Modules

Optional modules are enabled by creating files:

- `preferences.md` for soft preferences
- `changelog.md` for memory maintenance history
- `rules/<name>.md` for task rules
- `profiles/<name>.md` for workflow profiles
- `areas/<name>.md` for area-specific memory

Do not add optional files to default loading just because they exist. Load them only when the task matches.

## Conflict Rules

- Current user instruction overrides memory.
- Safety and permission constraints override memory.
- `do-not-use.md` overrides decisions and preferences.
- Hard constraints override preferences.
- Area memory can refine root memory, but must not override safety or hard constraints.
