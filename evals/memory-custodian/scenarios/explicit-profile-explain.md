# Explicit Profile Explain

## Purpose
Verify profile activation is explicit and traceable.

## Setup
Enable the `git` profile.

## Prompt
Read implementation context with `--profile git --explain`.

## Required Observations
- The profile loads with the explicit-profile reason code.

## Forbidden Outcomes
- Activating the profile without explicit input.

## Passing Criteria
Explain output identifies the explicit profile activation.
