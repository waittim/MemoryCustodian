# Constraints

- Must work without network access.
- Must not require RAG, embeddings, or vector databases.
- Must be reusable across Codex, Claude Code, and other agents.
- Must keep startup context small.
- Must store data locally as plain text.
- Must make memory easy to review, diff, commit, and roll back.
- Must keep default project initialization to the six core memory files.
- Must keep workflow-specific rules out of the core protocol.
