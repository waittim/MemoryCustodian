# Protocol 0.8 Codex Live Startup Smoke

- Date (UTC): 2026-09-26 06:05
- Agent: Codex app, GPT-6
- CLI: MemoryCustodian 0.12.0
- OS: macOS
- Repository baseline: `1fdebe599cecc412fab4c49bfe0a90b653c30829`
- Result: PASS for this one Codex startup observation

## Task and method

During the user-requested v0.12 release-gap repair, the live Codex agent read
`docs/memory/manifest.md` and `brief.md`, selected the canonical
`implementation` task, supplied planned paths, and received `COMPLETE` from
strict routing before editing. This was an existing task with prior context,
not a clean-session trial or a run of another agent adapter.

The reproducible read probe was:

```bash
bin/memory-custodian read --task implementation \
  --path cli/memory_custodian/read.py \
  --strict-routing --explain --no-local --format json
```

Exit code was `0`; stderr was empty. The JSON envelope had `status: PASS`.
Selected `data` fields were:

```json
{
  "routing_completeness": "COMPLETE",
  "loaded_modules": ["brief.md", "constraints.md", "decisions.md", "do-not-use.md", "preferences.md"],
  "skipped_modules": [],
  "conflict_status": "CLEAR",
  "context_sha256": "aad6ea60a6eb7cf4b6e23cf2f5d1cab7f3ad5d7767102ada22e781fb2071cb94"
}
```

The result included 17 stable Entry IDs and seven Subject IDs. The agent did
not load `inbox.md` or `archive/` into the context pack. The read itself did
not modify the repository.

## Evidence boundary

This is one observed Codex runtime using the current Protocol 0.8 repository.
It does not establish clean-session reliability, four-agent runtime parity,
semantic correctness, or a benchmark. The offline cross-agent fixture remains
the repeatable contract check for exact Entry IDs, Subject IDs, routing reasons,
conflict findings, context hash, and erasure scope. The separate cross-agent
recipe in `evals/memory-custodian/live-evaluation.md` has not been executed
for Claude Code, Gemini, or the generic adapter.
