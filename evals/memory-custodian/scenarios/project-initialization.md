# Project Initialization

## Purpose
Verify that initialization produces useful project memory instead of leaving protocol boilerplate as the default context.

## Setup
- A repository has a README and primary build metadata but no `docs/memory/` directory.
- The README describes the product, runtime, architecture, and current development direction.

## Prompt
The user says: "Initialize MemoryCustodian for this project."

## Required Observations
- Agent initializes the six core files.
- Agent curates `brief.md` from authoritative repository files before declaring memory ready.
- The brief describes the actual project purpose, direction, and system shape.
- Empty decisions, constraints, and tombstones remain empty rather than receiving MemoryCustodian product policy.

## Forbidden Outcomes
- Agent leaves TODOs or the legacy generic MemoryCustodian brief in place.
- Agent stores RAG, archive-loading, or platform-entry policy as product constraints without project-specific evidence.
- Agent claims initialization is complete while `brief.md` is still a scaffold.

## Passing Criteria
Pass when the initialized memory contains a concise real project brief and no protocol boilerplate masquerading as project knowledge.
