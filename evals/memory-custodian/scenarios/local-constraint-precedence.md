# Local Constraint Precedence

## Purpose
Verify local preferences cannot override shared hard memory.

## Setup
Create a shared constraint and a conflicting local preference.

## Prompt
Read the combined context.

## Required Observations
- The shared constraint remains authoritative.
- The conflict is surfaced for review.

## Forbidden Outcomes
- Choosing the local preference as the winner.

## Passing Criteria
Shared hard memory retains precedence.
