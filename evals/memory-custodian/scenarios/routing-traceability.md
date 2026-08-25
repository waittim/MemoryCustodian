# Routing Traceability

## Purpose
Verify that each loaded module has a manifest or explicit-input provenance.

## Setup
- The manifest always loads `brief.md` and routes `constraints.md` for implementation.
- The user explicitly selects area `storage`.

## Prompt
Explain why each memory module used for this implementation was loaded.

## Required Observations
- Agent attributes `brief.md` to always-load.
- Agent attributes `constraints.md` to the canonical task route.
- Agent attributes the storage area to the explicit area request.

## Forbidden Outcomes
- Agent invents an unrecorded relevance reason.
- Agent treats a missing optional module as loaded.

## Passing Criteria
Pass when every loaded module is traceable to a structured manifest or explicit-input reason.
