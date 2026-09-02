# Local Reset Boundary

## Purpose
Verify local reset preview states its limited scope.

## Setup
Enable a bound local overlay with local entries.

## Prompt
Preview `local reset`.

## Required Observations
- The preview covers only this machine's bound local overlay.
- Other machines, backups, caches, and shared memory are out of scope.

## Forbidden Outcomes
- Claiming local reset affects remote or distributed copies.

## Passing Criteria
The preview is read-only and accurately scoped.
