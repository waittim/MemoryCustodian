# Semantic Decision Compaction

## Purpose
Verify that budget maintenance preserves active invariants instead of archiving decisions solely by age.

## Setup
- `decisions.md` is over budget and contains several old but still-active subsystem invariants.
- `memory-custodian compact --target decisions.md` proposes archiving the oldest entries.

## Prompt
The user says: "Compact our project memory and keep it useful for future implementation work."

## Required Observations
- Agent reviews decision meaning before applying chronological archival.
- Agent merges superseded entries and moves subsystem knowledge into matched areas.
- Agent retains every active invariant in a normal task-loading path.
- Agent uses explicit age-based archival only after the proposed archive contains historical or inactive material.

## Forbidden Outcomes
- Agent immediately runs `--apply --archive-oldest` because the dry run fits the token budget.
- Agent moves an active invariant into explicit-only archive without another reachable copy.
- Agent raises budgets before attempting semantic consolidation or area splitting.

## Passing Criteria
Pass when active knowledge remains reachable, root memory is within budget, and only historical material is archived.
