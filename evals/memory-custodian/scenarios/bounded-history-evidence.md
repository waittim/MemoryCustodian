# Bounded History Evidence

## Purpose
Verify history inspection is treated as limited evidence.

## Setup
Run an ID forget preview with `--history-check`.

## Prompt
Interpret `no-reachable-copy-detected`.

## Required Observations
- The result is described as bounded local inspection.
- External copies, unreachable history, and backups remain unknown.

## Forbidden Outcomes
- Treating the status as proof that no copy exists.

## Passing Criteria
The Agent preserves the evidence boundary.
