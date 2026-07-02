# Do Not Use / Tombstones

## Tombstone: RAG/vector DB as MVP architecture
Status:
Do not reintroduce.
Reason:
The project explicitly targets pure-text memory files and lightweight implementation.
Applies to:
- MVP architecture
- Default installation

## Tombstone: Full memory in AGENTS.md or CLAUDE.md
Status:
Do not use.
Reason:
Agent instruction files should remain small entry points and should not carry full project memory.
Applies to:
- Codex adapter
- Claude Code adapter
- Generic adapter

## Tombstone: Git workflow as core protocol
Status:
Do not use.
Reason:
Git, release, ticket, and similar workflows should be optional profiles, not default core memory.
Applies to:
- Default manifest
- Initializer templates
- Core protocol documentation
