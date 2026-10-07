---
title: Group Shift Retry Confirmation
status: implemented
category: bug-fix
date: 2026-10-07
---

# Group Shift Retry Confirmation

## Contract

[INV-SCHED-25] Group shifts confirm their effective arrangement targets. A dynamic recovery target cancelled at the personal mood cap leaves the pending target map; fixed dormitory posts and unconfirmed working slots remain required. Shared replacement matching preserves all compatible candidates and respects reservations owned by other tasks.

[INV-SCHED-28] Explicit backup entry assignments retain priority through shared-slot revalidation, task coalescing and shift projection. Other shared slots retain ordinary complete-matching requirements.

## Implementation

`_prepare_group_shift` passes the union of other tasks' product reservations to `normalize_shared_arrangement`. The executing task retains access to its own reservations, while a name reserved by both tasks remains unavailable. Other callers retain the aggregate reservation filter. Candidate ordering places current and requested covers first without removing the remaining common candidates.

`prepare_dorm_selection` removes a matching pending recovery target when its existing personal-cap rule converts that dynamic bed to `Free`. The same target map survives retries and task serialization. Fixed posts and targets that have not completed recovery retain normal confirmation requirements. The existing matching, task ownership and release checks supply these boundaries without a second reservation or confirmation model.

`plan_metadata` applies the pending-confirmation guard at the shared queue-rebuilding entry point. A partial return remains queued with its original retry time even when another task's product reservation bypasses full shift convergence. Operator-specific stale-return cancellation retains these tasks until group confirmation, and backup evaluation waits for the completed arrangement. Shared revalidation continues to accept compatible zero-mood candidates; no additional mood filter changes that behavior.

Product reservation conflicts defer the entire arrangement when it carries group transitions or pending confirmation targets. The task retains its complete plan without creating a separately confirmed fragment. Tasks without group confirmation retain the existing slot-splitting behavior.

Automatic rescue handoff derives group transitions from final observed occupancy on an isolated projection. Feasibility, ordinary corrections and shared-slot matching run against that projection; only a completed handoff commits those transitions to live group state. Incomplete observations, pending specialized work and unfinished arrangements retain the prior state.

Shared matching excludes a replacement occupying another fixed dormitory post unless the arrangement explicitly releases that source slot. An occupant already covering the target shared post remains eligible. Ordinary recovery residents and compatible zero-mood replacements retain their existing eligibility.

Final dormitory selection relocates surviving confirmation targets by name after empty-slot compaction; temporary single-target recovery selections retain the final target map. Pending group confirmation preserves ordinary tasks while independently refreshing personal mood-limit releases from observed beds. Unchanged release sources retain their existing task object and retry time; changed observations replace the deadline and departed residents lose stale release tasks.

Timeout queue rebuilding retains tasks with pending group targets or active backup-shift arrangements, preserving object identity, remaining plans and retry times. These tasks do not themselves trigger ordinary timeout rebuilding.

Backup transition tasks record their explicit entry slots. Shift projection carries that task-local ownership through activation and retries; coalescing retains explicit assignments ahead of ordinary arrangements. Shared matching excludes only those slots from automatic replacement, and their assigned operators remain reserved for matching other slots. `Current` does not claim an explicit slot. Shared matching uses position and task reservations without querying mastery state.

## Verification

Offline regression tests cover the three failure paths, overlapping reservation owners, unavailable alternatives, complete matching across shared slots, unfinished recovery, missing working-slot observations and fixed dormitory targets. Existing shift, product, dormitory and personal-mood suites remain applicable. No live device or configuration changes participate in verification.

Additional regression tests exercise partial-return rebuilding through both scheduler and utility entry points, stale-return cancellation before state commit, resumption after confirmation, and zero-mood shared candidates through complete shift projection.

Exhaustion regression tests generate real future deadlines and verify empty arrangement plans, no replacement or bed reservations, and continued access to the same cover by ordinary groups. Execution uses the latest occupancy: a released cover allows direct departure, while an occupied alternate causes fresh coordination. The coordination retry retains an empty plan and generates the departure after support is confirmed. These tests preserve the existing execution-time coordination behavior without changing production scheduling or exhaustion deadlines.

Further regression cases cover whole-task product deferral for both shift directions, completion after reservation release, observed rescue returns and continued rest, interrupted rescue confirmation, and fixed dormitory cover protection with an explicit-source-release control.

Cap-confirmation regressions cover compacted dormitory targets, missing working slots, temporary selection isolation, both metadata entry points and backup-shift protection. Automatic-rescue mocks return an empty arrangement dictionary when no correction remains, matching the existing `return_plan=True` contract.

Timeout regressions cover overdue and future partial returns, backup-shift protection, preservation through metadata rebuilding and successful completion after the missing shared primary returns. Scheduler recovery tests retain their existing critical-task coverage.

Explicit-backup regressions cover generated tasks, projected activation, both coalescing directions, serialized partial group returns, placeholder exclusion and complete matching for other shared slots without duplicate assignments.
