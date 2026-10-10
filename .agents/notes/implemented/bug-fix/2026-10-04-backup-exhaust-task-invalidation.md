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

Backup coalescing requires concrete slot arrangements and cannot merge empty dynamic deadlines. Two live backup commit boundaries share scheduling signature comparison; projected swaps have no queue cleanup. Completion filters the existing candidate list without introducing another group-state API or changing lower-level bed allocation.

## Implementation

The effective signature includes group membership, assigned positions, replacements, operator role, personal mood limits, exhaustion and full-rest settings, and configured facility products. It excludes actual occupancy, current mood and timestamps. Both cached backup convergence and shift activation compare the previous signature only after successful plan changes. An immediate ordinary check wakes normal planning after affected deadlines are removed. A combined deadline is invalidated when any represented member changes.

## Verification

Focused offline tests cover backup activation and deactivation through both commit boundaries, unaffected and combined deadlines, staffing changes, failed activation, unchanged conditions, departed dormitory residents with named or Free replacements, workaholic members, incomplete groups and run-order recalculation. Tests use no device or network I/O.

## Standards Findings

Pass: shared commit-boundary comparison, bounded queue snapshots, actual occupancy isolation, focused offline verification and glossary synchronization using the user-approved wording. Ruff checks and the governance gate pass.

## Spec Findings

Pass: only changed effective staffing or exhaustion settings invalidate dynamic deadlines. The seven focused scheduler and governance suites pass on the alpha base with 342 tests and 24 subtests. Restoring the three original alpha dispatch methods in the offline test process reproduces ten failures for affected deadlines and departed dormitory residents. Unaffected deadlines, concrete arrangements, failed activation and projected changes retain their boundaries.
