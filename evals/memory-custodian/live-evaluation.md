# Reproducible Live Cross-Agent Evaluation

This is a live-runtime evaluation recipe, not a claim that the static checks
executed the four agents.  The offline fixture runner in
`scripts/check-skill-evals.py` exercises the same CLI contract for each named
adapter, but it is not a substitute for this live evaluation.

1. Check out the same commit on a clean machine and install package version `0.12.0`.
2. Disable local overlays or pass `--no-local`.
3. For Codex, Claude Code, Gemini, and a generic agent, give the adapter its normal entry file and the same prompt: implement a no-op review touching `cli/memory_custodian/read.py`.
4. Capture the exact CLI invocation and the JSON from `memory-custodian read --task implementation --path cli/memory_custodian/read.py --strict-routing --explain --no-local --format json`.
5. Compare each result with `cross-agent/shared-contract.json`. File sets, ordering, routing completeness, reason codes, Entry/Subject identities, conflict/reconciliation findings, and `context_sha256` must match byte-for-byte.
6. Record agent/runtime versions, OS, commit, UTC timestamp, and any deviation. A static adapter check is not a passing live result.

Store each reproducible result outside the fixture as an append-only evaluation
note. One current-protocol Codex startup observation is recorded in the
[Protocol 0.8 Codex smoke](../../docs/evaluations/protocol08-codex-live-smoke-2026-09-26.md); it used an
existing task and did not execute this clean cross-agent recipe. There is no
recorded live result for Claude Code, Gemini, or the generic adapter. The
offline fixture does not substitute for those runtime observations.
