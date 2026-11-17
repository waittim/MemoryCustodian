# Installed-Skill live smoke results

Generated: 2026-11-17T04:19:19.354811+00:00
Runtime: codex-cli 0.169.0-alpha.11.1; requested model: gpt-6.1-sol; reasoning: low.

Explicit installed Skill-file invocation only; automatic discovery was not tested.

| Task | Outcome | Evidence |
| --- | --- | --- |
| scoped-implementation | PASS | live-runtime |
| missing-scope | BLOCKER | live-runtime-unavailable |
| unconfirmed-observation | BLOCKER | live-runtime-unavailable |

Three development tasks, one independent session each. Failures and blockers are retained.
This is a single-runtime workflow smoke, not effectiveness, cross-agent conformance, or checkpoint evidence.
Strict-read proofs require CLI JSON content and observable event order; command mentions alone are insufficient.
Raw prompts, commands, output, reasoning, messages and machine paths are not retained.
Source/fixture hashes and allowlisted metadata support consistency, not tamper-proof runtime attestation.
