---
title: Group Shift Retry Confirmation
status: implemented
category: bug-fix
date: 2026-10-07
---

# Group Shift Retry Confirmation

## Contract

[INV-SCHED-25] Group shifts confirm their effective arrangement targets. A dynamic recovery target cancelled at the personal mood cap leaves the pending target map; fixed dormitory posts and unconfirmed working slots remain required. Shared replacement matching preserves all compatible candidates and respects reservations owned by other tasks.

## Implementation

`_prepare_group_shift` passes the union of other tasks' product reservations to `normalize_shared_arrangement`. The executing task retains access to its own reservations, while a name reserved by both tasks remains unavailable. Other callers retain the aggregate reservation filter. Candidate ordering places current and requested covers first without removing the remaining common candidates.

`prepare_dorm_selection` removes a matching pending recovery target when its existing personal-cap rule converts that dynamic bed to `Free`. The same target map survives retries and task serialization. Fixed posts and targets that have not completed recovery retain normal confirmation requirements. The existing matching, task ownership and release checks supply these boundaries without a second reservation or confirmation model.

`plan_metadata` applies the pending-confirmation guard at the shared queue-rebuilding entry point. A partial return remains queued with its original retry time even when another task's product reservation bypasses full shift convergence. Operator-specific stale-return cancellation retains these tasks until group confirmation, and backup evaluation waits for the completed arrangement. Shared revalidation continues to accept compatible zero-mood candidates; no additional mood filter changes that behavior.

## Verification

Offline regression tests cover the three failure paths, overlapping reservation owners, unavailable alternatives, complete matching across shared slots, unfinished recovery, missing working-slot observations and fixed dormitory targets. Existing shift, product, dormitory and personal-mood suites remain applicable. No live device or configuration changes participate in verification.

Additional regression tests exercise partial-return rebuilding through both scheduler and utility entry points, stale-return cancellation before state commit, resumption after confirmation, and zero-mood shared candidates through complete shift projection.
