# Duplicate Structural Owner

## Purpose
Verify uniqueness of active Scope, Subject, and Facet ownership.

## Setup
- An active project-scoped decision owns a Subject's `version-policy` Facet.

## Prompt
Add another active decision with the same Scope, Subject ID, and Facet.

## Required Observations
- Agent identifies the existing structural owner.
- Agent proposes superseding it, changing Scope, or reviewing the Subject.

## Forbidden Outcomes
- Agent creates a second active owner.
- Agent treats different body wording as a separate identity.

## Passing Criteria
Pass when the duplicate is rejected unless an explicit valid supersede transition is used.
