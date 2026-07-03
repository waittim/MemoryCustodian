# Constraints

- Must work without network access.
- Must store project memory as local Markdown files under `docs/memory/`.
- Must not introduce RAG, embeddings, vector databases, or cloud memory for the MVP unless explicitly requested.
- Must be reusable across Codex, Claude Code, and other agents.
- Must keep startup context small.
- Must make memory easy to review, diff, commit, and roll back.
- Must keep default project initialization to the six core memory files.
- Must keep workflow-specific rules out of the core protocol.
- Must keep Skill instructions concise and operational; detailed non-goals belong in README and references.
