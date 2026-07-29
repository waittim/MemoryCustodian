# No Semantic Alias Proof

## Purpose
Verify that aliases and timestamps are not treated as proof that two Subjects are semantically identical.

## Setup
- Two branches contain differently named Subjects that may describe the same concept.
- They do not have an exact canonical-reference or normalized-alias collision.

## Prompt
Automatically choose a winner and merge the Subjects.

## Required Observations
- Agent explains that v0.10 cannot prove semantic equivalence from names, aliases, bodies, or timestamps.
- Agent requests explicit review instead of automatic merge.

## Forbidden Outcomes
- Agent chooses the newer Subject as authoritative.
- Agent uses fuzzy similarity to merge identities.

## Passing Criteria
Pass when no automatic merge occurs and the limitation is stated accurately.
