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

## 2026-07-28 - From decisions.md
Reason:
Version-specific protocol and bootstrap choices are historical after Protocol 0.6 adoption.

## MC-DEC-20260719-59d6d8ed — Keep Protocol 0.5 for v0.9

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Keep the memory protocol at 0.5 while package 0.9 removes CLI semantic guessing and hardens mutation safety.
Reason:
Manifest schema and routing syntax remain compatible with existing 0.5 projects.

## MC-DEC-20260718-491db2c3 — Protocol 0.5

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Keep for v0.8.
Reason:
Existing manifests support strict routing.

## MC-DEC-20260704-a4ce76c2 — Add lightweight plugin bootstrap and deterministic packaging

Status: active
Scope: project
Evidence:
- legacy-unverified

Decision:
Add a thin session-start bootstrap and deterministic Codex archive packaging while keeping memory protocol 0.4.
Reason:
Startup should nudge manifest-first loading without injecting full skill text or memory; package versions may advance separately.
