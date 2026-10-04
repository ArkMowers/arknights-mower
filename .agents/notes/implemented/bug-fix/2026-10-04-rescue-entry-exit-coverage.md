---
title: Rescue Entry and Exit Coverage
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue Entry and Exit Coverage

## Contract

Existing [INV-SCHED-09] includes measured low-mood primaries already resting in startup contention. Normal handoff plans reserve replacements and beds together for unfinished groups. Unknown measurements do not establish infeasibility. Measured target completion still requires feasible normal staffing and rotation before exit.

## Simplification

Startup reuses the existing resting-handoff planner and staffing validator. Its validation checks current coverage; exit retains future rotation checks. No new scheduler, configuration or glossary term is introduced. Future groups may rotate sequentially; unfinished groups require simultaneous coverage.

## Implementation

When normal coverage is feasible at startup, one normal correction carries the verified handoff instead of recalling unfinished primaries. It replaces ordinary staffing tasks while preserving product switches and specialized tasks. When coverage is blocked, the existing rescue entry persists the episode. Exit evaluates the normal roster, including restored dormitory capacity, before starting handoff.

## Verification

Offline tests cover already-resting low groups with available or exhausted replacements, preservation of resting primaries during startup handoff, unknown readings, shared replacement conflicts and completed targets without viable normal rotation. Existing personal-limit and specialized-compensation tests remain enforced.

## Standards Findings

Projection uses isolated mutable state and the read-only expression evaluator. Existing [INV-SCHED-09] and [INV-SCHED-14] remain authoritative.

## Spec Findings

Bed occupancy alone neither suppresses rescue entry nor permits exit. No remote deployment or live-device tests are performed.
