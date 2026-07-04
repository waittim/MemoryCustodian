# Optional Modules

## Purpose
Verify that optional rules, profiles, and areas remain discoverable through the manifest but are not loaded by default.

## Setup
- A project has optional files under `rules/`, `profiles/`, or `areas/`.
- The manifest contains an optional module index.
- The current task does not match any optional module.

## Prompt
The user asks for a general status check of project memory.

## Required Observations
- Agent discovers optional modules from `manifest.md`.
- Agent does not load optional module contents unless the task or user request matches.
- Agent reports unindexed optional files as a memory health issue.
- Agent keeps workflow-specific rules out of the core protocol.

## Forbidden Outcomes
- Agent loads every optional file during general status.
- Agent treats Git, release, ticket, or similar workflows as core protocol.
- Agent ignores optional files that exist but are missing from the manifest index.

## Passing Criteria
Pass when optional modules are indexed and discoverable, but only matching modules are loaded.
