# Explain Skipped Reasons

## Purpose
Verify every enabled module has an observable disposition.

## Setup
Enable rule, profile, and area modules with different activations.

## Prompt
Run a routed read with `--explain`.

## Required Observations
- Loaded, skipped, missing, or invalid modules include stable reason codes.
- Skipped enabled modules remain visible.

## Forbidden Outcomes
- Reporting only loaded modules.

## Passing Criteria
Each enabled module has exactly one final disposition.
