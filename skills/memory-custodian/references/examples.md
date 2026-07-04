# Examples

## Minimal Context Pack

```markdown
# Memory Context Pack
Task: default
Loaded:
- brief.md

## brief.md
MemoryCustodian is a local-first, pure-text project memory skill and CLI.
```

## Planning Context Pack

```markdown
# Memory Context Pack
Task: planning
Loaded:
- brief.md
- decisions.md
- constraints.md
- do-not-use.md
```

## Artifact Context Pack

```markdown
# Memory Context Pack
Task: artifact
Loaded:
- brief.md
- rules/output.md
- preferences.md
- do-not-use.md
```

## Decision Entry

```markdown
## 2026-06-30 - Use plain text memory files
Decision:
Store memory as markdown files inside each project.
Reason:
This keeps memory local, inspectable, portable, and easy to version with git.
```

## Tombstone Entry

```markdown
## Tombstone: RAG/vector DB as MVP architecture
Do not reintroduce unless the user explicitly reverses this. Reason: the project targets pure-text memory files and lightweight implementation. Date: 2026-06-30.
```
