---
title: Rescue backup condition
status: archived
category: feature
date: 2026-09-30
---

Superseded by [Native automatic rescue](../../archived/simplification/2026-10-02-native-automatic-rescue.md).


# Rescue backup condition

## Contract

[INV-SCHED-09] Rescue Recovery Lifecycle uses the main plan's individual mood limits and a majority-completion latch. The boolean `op_data.rescue_needed()` integrates with ordinary backup expressions, without a mandatory backup entry, fixed priority, or new plan schema. Active rescue backups assign explicit workers as zero-mood workers without replacements. Main primaries and priority replacements receive the highest resting tier; exclusions win. Unconfigured rescue retains ordinary rotation and uses existing vacant Free beds without batch clearing.

[INV-SCHED-10] Completed Exhaust Continuation returns from an already-completed exhausted-shift task without `skip()`, so normal run-order planning remains reachable.

## Boundary and simplification

The unified scheduler owns all dormitory allocation. The rescue condition reuses backup convergence, shared resting tiers, and existing bed ownership. It introduces neither retired dorm modes nor a dorm-clearing task. Main-plan identity and mood limits remain independent of temporary rescue assignments. Each projection owns its rescue completion set. A completed episode rearms after the low-mood population falls below the entry boundary, preventing immediate convergence oscillation.

## Verification

Hermetic tests cover individual limits, unknown readings, strict-majority exit, projection isolation, ordinary fallback, priority and exclusion rules, missing rescue replacements, backup round trips, occupied-bed preservation, group and replacement recovery deadlines, restart identity, and residual exhausted tasks restoring run-order planning. Existing residents leave at their individual caps through ordinary release tasks, without batch clearing. UI tests cover the optional boolean condition and its assignment rules.
