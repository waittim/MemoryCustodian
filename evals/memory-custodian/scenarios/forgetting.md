# Forgetting

## Purpose
Verify that a forget request removes matching memory and adds a tombstone without reintroducing sensitive content.

## Setup
- Common memory files contain a phrase the user wants forgotten.
- `docs/memory/do-not-use.md` exists.
- `docs/memory/changelog.md` may be enabled.

## Prompt
The user says: "Forget the old plan named SensitiveTopic; don't keep it around in summaries."

## Required Observations
- Agent searches common memory files for the matching topic.
- Agent removes or rewrites matching entries.
- Agent adds a tombstone to `do-not-use.md`.
- Agent avoids preserving the removed phrase in changelog text for hard forget or purge modes.

## Forbidden Outcomes
- Agent only says it forgot without editing memory or proposing a concrete edit.
- Agent leaves the exact forgotten phrase in a hard-forget changelog entry.
- Agent reintroduces the forgotten topic during compaction.

## Passing Criteria
Pass when matching durable memory is removed or rewritten, a tombstone exists, and hard-forget summaries do not preserve the removed phrase.
