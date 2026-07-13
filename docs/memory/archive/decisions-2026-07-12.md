# Archived Memory: decisions.md

## 2026-07-12 - From decisions.md
Reason:
Active memory exceeded its context budget; older complete entries were moved to explicit-only archive.

## 2026-06-30 - Use local text memory
Decision:
Store durable project memory as Markdown under `docs/`, defaulting to `docs/memory/`; keep agent entry files thin.
Reason:
Memory should be local, inspectable, portable, diffable, and easy to roll back.
