# Scoped Memory Update

## Purpose
Verify that subsystem decisions remain retrievable without bloating the root decision log.

## Setup
- A large application already uses MemoryCustodian.
- Its manifest has no sync area yet.
- During implementation, the user confirms a durable retry invariant that applies only to synchronization.

## Prompt
The user says: "Sync retries use persisted exponential backoff and quarantine after eight failures. Remember this for future sync work."

## Required Observations
- Agent classifies scope before content type.
- Agent creates or updates `areas/sync.md` with the decision and reason.
- Agent indexes the area in `manifest.md` with a sync-related trigger.
- Agent ensures later sync implementation or debugging work loads the matched area.

## Forbidden Outcomes
- Agent appends the subsystem-only decision only to root `decisions.md`.
- Agent adds the area to default loading for unrelated work.
- Agent records the statement only in chat or `inbox.md` despite clear durability.

## Passing Criteria
Pass when the sync decision is durable, indexed, and reachable for sync tasks without entering unrelated context packs.
