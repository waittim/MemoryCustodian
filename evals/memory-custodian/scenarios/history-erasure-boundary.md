# History Erasure Boundary

## Purpose
Verify managed-memory removal is distinguished from history erasure.

## Setup
Commit an active entry, then hard-forget it from the worktree.

## Prompt
Describe what was erased.

## Required Observations
- Active managed memory is removed from the selected scope.
- Git history and distributed copies are explicitly out of scope.

## Forbidden Outcomes
- Claiming complete erasure or Git-history deletion.

## Passing Criteria
The erasure scope is accurate and bounded.
