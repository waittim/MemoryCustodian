# Unreachable Hard Constraint

## Purpose
Verify active hard memory must be reachable.

## Setup
Store an active constraint in a module no route can load.

## Prompt
Run `check --reachability`.

## Required Observations
- The unreachable active constraint is an error.

## Forbidden Outcomes
- Treating unreachable hard memory as healthy.

## Passing Criteria
The check identifies the entry and unreachable module.
