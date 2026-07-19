# Manifest Policy

`manifest.md` is the sole runtime routing authority for MemoryCustodian. It tells an agent which memory files may enter context for a task.

## Responsibilities

- Define the default memory files.
- Map task types to additional files.
- Maintain a lightweight index of enabled optional rules, profiles, and areas.
- Mark `archive/` as explicit-only.
- State context budgets.

The manifest should not contain full project memory, decision history, or long rules. Put durable content in the relevant memory file and keep the manifest short. Optional module entries should be short discovery hints, not summaries of the optional file contents.

## Generated Defaults

The generated manifest normally loads `brief.md` and keeps inbox, archive, and unrelated optional modules out of default context. These are template defaults, not a second routing definition. Always follow the current project's manifest when it differs.

## Task Routing

Identify the requested category, such as planning, implementation, artifact work, preferences, history, or maintenance, and resolve its files from the project manifest. Never supplement a valid custom route from a built-in table, example, adapter, or remembered default.

If no memory directory exists, normal project work may continue without memory. If the directory exists but `manifest.md` is missing, stop memory loading and report the setup as incomplete or corrupted. Do not guess routes from filenames.

## Optional Modules

Optional modules are enabled by creating files and listing task-scoped modules in the optional module index:

- `preferences.md` for soft preferences
- `changelog.md` for memory maintenance history
- `rules/<name>.md` for task rules
- `profiles/<name>.md` for workflow profiles
- `areas/<name>.md` for area-specific memory

The optional module index should list enabled `rules/`, `profiles/`, and `areas/` files with a short trigger condition. This lets agents discover available optional memory by reading `manifest.md` while keeping the optional file contents out of startup context.

Do not add optional files to default loading just because they exist. Load them only when the task matches the index trigger or the user explicitly requests them.

Area matching takes precedence over loading every root decision. Use the manifest hint plus touched files or task scope to select only relevant areas.

## Conflict Rules

- Current user instruction overrides memory.
- Safety and permission constraints override memory.
- `do-not-use.md` overrides decisions and preferences.
- Hard constraints override preferences.
- Area memory can refine root memory, but must not override safety or hard constraints.
