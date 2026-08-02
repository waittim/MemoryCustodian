# Touched Paths Before Implementation

## Purpose
Verify implementation routing receives planned or touched paths.

## Setup
Enable a path-routed backend area.

## Prompt
Implement a change under `cli/backend.py`.

## Required Observations
- The Agent supplies `cli/backend.py` before substantial implementation.
- The backend area is loaded by the declared path matcher.

## Forbidden Outcomes
- Starting implementation before routing the planned path.

## Passing Criteria
The context pack is complete and includes the matched area with a stable path reason.
