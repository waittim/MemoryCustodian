# Manifest Policy

`manifest.md` is the routing layer for MemoryCustodian. It tells an agent which memory files may enter context for a task.

## Responsibilities

- Define the default memory files.
- Map task types to additional files.
- Maintain a lightweight index of enabled optional rules, profiles, and areas.
- Mark `archive/` as explicit-only.
- State context budgets.

The manifest should not contain full project memory, decision history, or long rules. Put durable content in the relevant memory file and keep the manifest short. Optional module entries should be short discovery hints, not summaries of the optional file contents.

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
- Implementation / execution / debugging: `constraints.md`, `do-not-use.md`, and `preferences.md` if present
- User-facing artifact / output: `do-not-use.md`, `rules/output.md` if present, and `preferences.md` if present
- Preferences: `preferences.md` if present
- Recap / history: `decisions.md` and `changelog.md` if present
- Memory maintenance: `inbox.md`, `do-not-use.md`, and `changelog.md` if present

## Optional Modules

Optional modules are enabled by creating files and listing task-scoped modules in the optional module index:

- `preferences.md` for soft preferences
- `changelog.md` for memory maintenance history
- `rules/<name>.md` for task rules
- `profiles/<name>.md` for workflow profiles
- `areas/<name>.md` for area-specific memory

The optional module index should list enabled `rules/`, `profiles/`, and `areas/` files with a short trigger condition. This lets agents discover available optional memory by reading `manifest.md` while keeping the optional file contents out of startup context.

Do not add optional files to default loading just because they exist. Load them only when the task matches the index trigger or the user explicitly requests them.

## Conflict Rules

- Current user instruction overrides memory.
- Safety and permission constraints override memory.
- `do-not-use.md` overrides decisions and preferences.
- Hard constraints override preferences.
- Area memory can refine root memory, but must not override safety or hard constraints.
