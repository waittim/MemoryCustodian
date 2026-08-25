# Archived Memory: decisions.md

Complete historical entries moved from active memory after reviewed compaction.
This file is explicit-only and is not part of normal task context.

## 2026-06-30 - Use local text memory
Decision:
Store durable project memory as Markdown under `docs/`, defaulting to `docs/memory/`; keep agent entry files thin.
Reason:
Memory should be local, inspectable, portable, diffable, and easy to roll back.
