# Archived Memory: decisions.md

## 2026-07-28 - From decisions.md
Reason:
Active memory exceeded its context budget; older complete entries were moved to explicit-only archive.

## MC-DEC-20260704-b2b839a6 — Use project-memory card branding

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Use stacked index-card branding with a near-black background and short blue bookmark marker.
Reason:
Signal local project memory and manifest-driven retrieval, not CI validation.

## MC-DEC-20260704-897ff460 — Make plugin distribution self-contained

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Codex plugin support includes repo-local marketplace metadata, plugin metadata/assets, and a bundled CLI wrapper. Project memory stays in `docs/memory/`.
Reason:
Plugin install should expose the workflow and helper CLI without copying project memory.

## MC-DEC-20260703-2285865c — Version package and memory protocol separately

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Track package/plugin version separately from memory protocol version. Manifests record protocol metadata.
Reason:
CLI or skill updates must not silently mutate existing project memory.

## MC-DEC-20260703-d403d087 — Separate offline memory from distribution

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Memory operations work offline by default; installation/update flows may use network distribution.
Reason:
Runtime memory stays local-first while updates can use marketplaces, package managers, or git.
