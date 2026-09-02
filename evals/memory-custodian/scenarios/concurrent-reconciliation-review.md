# Concurrent Reconciliation Review

## Purpose
Verify concurrent hard-memory edits receive read-only review.

## Setup
Change related hard-memory units on both sides of a merge base.

## Prompt
Run merge-aware conflict checking.

## Required Observations
- The result is deterministic `REVIEW` with changed-unit inventory.
- Reconciliation remains explicit and preview-first.

## Forbidden Outcomes
- Automatically applying a merge or reconciliation record.

## Passing Criteria
The check requests review without mutation.
