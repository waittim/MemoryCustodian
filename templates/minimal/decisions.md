# Decisions

## YYYY-MM-DD - Use MemoryCustodian
Decision:
Use MemoryCustodian for repo-native project memory.

Reason:
Project memory should be local, plain-text, inspectable, and reusable across agents.

Implications:
- Keep platform entry files short.
- Store durable context in `docs/memory/`.
- Avoid RAG or vector DB in MVP.

Status:
active
