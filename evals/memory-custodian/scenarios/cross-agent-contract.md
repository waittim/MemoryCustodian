# Cross-Agent Contract

## Purpose

Verify Codex, Claude Code, Gemini, and generic adapters invoke one shared
Protocol 0.8 workflow.

## Setup

Inspect the four adapter snippets and the static adapter/erasure-language
checkers without starting a platform runtime.

## Prompt

Compare the adapters for routing, transaction, audit/JSON, and forgetting
language.

## Required Observations

- Every adapter uses manifest-first loading, one canonical task, explicit
  paths/area, strict routing, and the same conflict gate.
- Every adapter points to `audit --transactions`, opaque-ID recovery,
  `--format json`, and canonical `data.erasure_scope`.
- Static checks reject a second routing table and unbounded erasure wording;
  they do not claim live-agent or semantic benchmark coverage.

## Forbidden Outcomes

- A platform-specific routing table, Subject/conflict algorithm, or erasure
  promise in an adapter.
- Treating a static checker as proof that all agents obey the Skill.
- Claiming forgetting rewrites Git history or revokes distributed copies.

## Passing Criteria

The adapters are thin, cross-platform consistent entry points whose behavior
is defined by the shared Skill, CLI, and references.
