---
title: Backup Exhaust Task Invalidation
status: implemented
category: bug-fix
date: 2026-10-04
---

# Backup Exhaust Task Invalidation

## Contract

[INV-SCHED-10] preserves normal planning when all recovery-requiring working members already rest. Configured dormitory residents and workaholics do not block completed exhausted shifts; at least one recovery-requiring working member is required for completion.

Successful backup activation or deactivation invalidates an empty-plan EXHAUST_OFF deadline only when its named operators or their group members change effective staffing or exhaustion settings. Unaffected deadlines and concrete arrangements remain queued. Failed convergence, failed activation, unchanged conditions and projections preserve the queue and actual occupancy. Normal planning rebuilds affected deadlines from the effective schedule and confirmed occupancy.

## Pre-flight Simplification

Backup coalescing requires concrete slot arrangements and cannot merge empty dynamic deadlines. Two live backup commit boundaries and the private complete-shift projection queue share scheduling signature comparison; projected swaps preserve the live queue. Completion filters the existing candidate list without introducing another group-state API or changing lower-level bed allocation.

## Implementation

The effective signature includes group membership, assigned positions, replacements, operator role, personal mood limits, exhaustion and full-rest settings, and configured facility products. It excludes actual occupancy, current mood and timestamps. Both cached backup convergence and shift activation compare the previous signature only after successful plan changes. An immediate ordinary check wakes normal planning after affected deadlines are removed. A combined deadline is invalidated when any represented member changes.

Complete-shift projection previously changed effective configuration while repeatedly copying the original pending deadlines into rotation and bed planning. It now removes affected deadlines from its private pending list after each successful projected swap. Filtering that list prevents later rounds and final bed filling from restoring an invalidated deadline. The live queue remains available if projection fails, and retained execution and concrete arrangements keep their existing protection. [Projection regressions](../../../../arknights_mower/tests/backup_exhaust_projection_tests.py) cover due and future deadlines, combined requests, repeated planning, backup reactivation, retained work and failure isolation; they do not reproduce a specific account's staffing outcome without its schedule and observations.

## Verification

Focused offline tests cover backup activation and deactivation through both commit boundaries, unaffected and combined deadlines, staffing changes, failed activation, unchanged conditions, departed dormitory residents with named or Free replacements, workaholic members, incomplete groups and run-order recalculation. Tests use no device or network I/O.

## Standards Findings

Pass: shared commit-boundary comparison, bounded queue snapshots, actual occupancy isolation, focused offline verification and glossary synchronization using the user-approved wording. Ruff checks and the governance gate pass.

## Spec Findings

Pass: only changed effective staffing or exhaustion settings invalidate dynamic deadlines. The seven focused scheduler and governance suites pass on the alpha base with 342 tests and 24 subtests. Restoring the three original alpha dispatch methods in the offline test process reproduces ten failures for affected deadlines and departed dormitory residents. Unaffected deadlines, concrete arrangements, failed activation and projected changes retain their boundaries.

## Refresh rules during physical arrangements

Backup configuration becomes effective before the physical arrangement completes. Removing a refresh operator at that point previously suppressed its departure callback, leaving an exhaustion deadline based on the old depletion rate or an old trade-order deadline. The arrangement task retains the preceding refresh rules until actual moves are confirmed, using the union with the effective rules. Room-qualified trade refreshes preserve their target rooms. A deferred task retains this information for resumed execution; completed arrangements discard it.

Invalidating every deadline when a refresh list changes cannot establish the post-arrangement rate or order time, because actual occupancy is still unchanged. Retaining transition rules lets the existing observation callbacks refresh the affected deadlines at the actual move. It also avoids persistent configuration changes and a second callback implementation. This extends the same backup deadline decision; domain concepts and glossary definitions remain unchanged. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md#backup-refresh-continuity) defines the execution and isolation requirements.

Focused offline regression coverage exercises both activation paths, actual `infra_main` dispatch and departure callbacks, scoped and unrestricted trade refreshes, task coalescing, serialized retry, deferred or failed arrangements, and completion cleanup. The review confirms that configuration-only changes and preview cannot refresh the real queue. These tests mock device operations and do not establish live-device timing.
