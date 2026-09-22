# Do Not Use / Tombstones

Tombstones are newest first.

## MC-DNU-20260921-54000001 — SQLite session persistence

Status: active
Scope: project
Subject: MC-SUBJ-20260921-51000001
Facet: architecture
Evidence:
- user-confirmed

Rejected:
Do not reintroduce SQLite for session persistence unless the user explicitly reverses this decision.

Reason:
The current data size does not justify a database, and portability is a product requirement.
