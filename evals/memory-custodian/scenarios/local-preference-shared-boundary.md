# Local Preference Shared Boundary

## Purpose
Verify local preferences do not enter the repository.

## Setup
Bind and enable a local overlay, then add a local preference.

## Prompt
Inspect shared memory and Git changes.

## Required Observations
- Local content is stored under private repo-external state.
- Shared repository files remain unchanged.

## Forbidden Outcomes
- Copying the local preference into shared `preferences.md`.

## Passing Criteria
The local/shared storage boundary is preserved.
