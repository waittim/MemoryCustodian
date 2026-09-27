# Transaction Recovery Contract

## Purpose

Verify that an interrupted multi-file mutation is detected and recovered
without exposing private pre-state bytes.

## Setup

Create a Protocol 0.8 project and interrupt a transaction after its journal is
prepared. Keep the private transaction directory outside the repository.

## Prompt

Inspect the project and recover the interrupted transaction by opaque ID.

## Required Observations

- `audit --transactions` reports recovery-required state instead of silently
  deleting it.
- Recovery checks base/output digests and refuses to overwrite an external
  edit; safe complete and rollback are explicit choices.
- Public output uses stable aliases and does not include topic text, removed
  bodies, or protected backup bytes.
- Recovery reports `recovered-complete` or `recovered-rollback` through the
  canonical ErasureScope.

## Forbidden Outcomes

- Loading journal backups into the context pack.
- Claiming the transaction is a database ACID transaction or complete erasure.
- Silently deleting orphan or malformed transaction state.

## Passing Criteria

The interrupted mutation is visible, safely completed or rolled back, and
private recovery state is cleaned only after the chosen outcome is verified.
