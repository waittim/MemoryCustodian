# Concurrent Write Safety
## Purpose
Prevent silent lost updates.
## Setup
Two processes add evidence-backed decisions.
## Prompt
Run both writes concurrently.
## Required Observations
- Preserve both entries or return a clear lock timeout for one process.
## Forbidden Outcomes
- Report two successes while retaining one entry.
## Passing Criteria
The memory file is intact and no update is silently lost.
