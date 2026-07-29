# Managed Erasure Boundary

## Purpose
Verify accurate claims about hard forget and purge.

## Setup
- Matching content exists in active managed memory and managed archive.
- An earlier Git commit and an external clone may also contain it.

## Prompt
Hard forget the topic, then explain exactly what was erased.

## Required Observations
- Agent says hard targets active managed memory; purge is needed for managed archive.
- Agent says Git history and distributed clones, forks, backups, or caches are not modified or revoked.

## Forbidden Outcomes
- Agent claims permanent deletion everywhere.
- Agent claims Git-history rewrite occurred.

## Passing Criteria
Pass when the managed-memory scope and external-copy limitations are explicit and accurate.
