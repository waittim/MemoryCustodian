# Decisions

## YYYY-MM-DD - Use MemoryCustodian
Decision:
Use local Markdown files under `docs/memory/` for durable project memory. Keep platform entry files short bootstraps.

Reason:
Memory should be inspectable, diffable, portable, and reusable across agents.

Implications:
- Load context through `manifest.md`.
- Avoid RAG or vector DB in MVP.
