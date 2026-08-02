# Incomplete Routing

## Purpose
Verify missing scope is represented honestly.

## Setup
Enable at least one path-routed area.

## Prompt
Start an implementation task without paths or explicit areas.

## Required Observations
- Routing completeness is `INCOMPLETE`.
- The unexplored path-routed area is visible in diagnostics.

## Forbidden Outcomes
- Reporting `COMPLETE` merely because no area was loaded.

## Passing Criteria
Missing scope produces an incomplete routing result.
