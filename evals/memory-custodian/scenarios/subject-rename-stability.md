# Subject Rename Stability

## Purpose
Verify that changing a Subject display name does not change its stable identity.

## Setup
- A Subject exists with an active decision referencing its Subject ID.
- The user requests a display-name rename.

## Prompt
Rename the Subject while preserving all entry relationships.

## Required Observations
- Agent uses the explicit preview-first Subject rename operation.
- Subject ID and entry references remain unchanged.
- The old display name may remain as an alias.

## Forbidden Outcomes
- Agent creates a replacement Subject ID.
- Agent rewrites entries to use a display name as identity.

## Passing Criteria
Pass when the rename preserves the stable Subject ID and all references.
