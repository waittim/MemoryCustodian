# JSON and ErasureScope Contract

## Purpose

Verify stable Protocol 0.8 machine output and the shared erasure boundary.

## Setup

Prepare a forget, hard/purge, local-reset, or recovery preview in a Protocol
0.8 project.

## Prompt

Request the result with `--format json` and explain its scope.

## Required Observations

- stdout contains one JSON envelope with `output_schema_version: 1`,
  `status`, `exit_class`, `data`, `findings`, and `disclaimers`.
- Audit data uses `audit_schema_version: 1`; forgetting/local-reset/recovery
  data uses `erasure_scope_schema_version: 1` with every canonical field.
- `unavailable` history inspection is REVIEW rather than PASS, and bounded
  `no-reachable-copy-detected` does not prove external copies are absent.
- Text and JSON describe the same result and do not serialize the internal
  execution plan.

## Forbidden Outcomes

- Omitting an ErasureScope field or using null for a documented enum state.
- Emitting topic-bearing hard/purge plan metadata, protected backup bytes, or
  machine-absolute private paths.
- Claiming Git history or distributed copies were erased or revoked.

## Passing Criteria

The JSON is deterministic, schema-versioned, privacy-bounded, and uses the
same managed-memory boundary as the text result.
