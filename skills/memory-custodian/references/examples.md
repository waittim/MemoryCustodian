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

Create or select the stable Subject first:

```markdown
## MC-SUBJ-20260729-a1b2c3d4 — Memory storage model

Status: active
Kind: concept
Evidence:
- user-confirmed

Aliases:
- Memory storage model
```

```markdown
## MC-DEC-20260630-a1b2c3d4 — Use plain text memory files

Status: active
Scope: project
Subject: MC-SUBJ-20260729-a1b2c3d4
Facet: architecture
Evidence:
- user-confirmed

Decision:
Store memory as markdown files inside each project.
Reason:
This keeps memory local, inspectable, portable, and easy to version with git.
```

Keep the complete entry within 120 tokens. Put detailed consequences in constraints, matched area context, or source documentation rather than adding a long `Implications` narrative.

## Tombstone Entry

```markdown
## MC-DNU-20260630-b2c3d4e5 — Tombstone: RAG/vector DB as MVP architecture

Status: active
Scope: project
Subject: MC-SUBJ-20260729-b2c3d4e5
Facet: adoption-policy
Evidence:
- user-confirmed

Rejected:
Do not reintroduce unless the user explicitly reverses this.
```
