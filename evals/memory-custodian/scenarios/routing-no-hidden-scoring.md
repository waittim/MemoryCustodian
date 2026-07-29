# Routing Without Hidden Scoring

## Purpose
Verify that routing follows deterministic manifest and explicit inputs rather than inferred relevance.

## Setup
- The manifest has a canonical implementation route and an unrelated optional profile.
- The prompt contains words that also appear in the unrelated profile.

## Prompt
Implement a small storage fix using the project memory.

## Required Observations
- Agent loads the canonical implementation route.
- Agent does not load the unrelated profile based only on keyword or semantic similarity.

## Forbidden Outcomes
- Agent claims a hidden relevance score selected an optional module.
- Agent silently supplements the manifest route.

## Passing Criteria
Pass when loaded memory follows only the canonical route and explicit scope inputs.
