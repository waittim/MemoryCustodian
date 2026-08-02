# No Prose Area Inference

## Purpose
Verify free-text task wording does not activate an area.

## Setup
Enable a backend area for `cli/backend/**`.

## Prompt
Discuss a backend change without supplying paths or an explicit area.

## Required Observations
- The Agent reports incomplete scope for substantial work.
- Area activation requires paths or an explicit area.

## Forbidden Outcomes
- Loading the backend area because the prompt contains “backend”.

## Passing Criteria
No prose-based area inference occurs.
