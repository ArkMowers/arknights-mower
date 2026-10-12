---
title: Recovery Release and Task Retention
status: implemented
category: bug-fix
date: 2026-10-01
---

# Recovery Release and Task Retention

## Contract

[INV-DEV-19] leaves the shared ADB server running during process shutdown and idle cleanup. [Device Control](../../../../docs/subsystems/device-control.md) defines application-owned helper release, deferred cleanup and idempotent closure. The [shared ADB recovery decision](../../implemented/simplification/2026-10-01-shared-adb-recovery.md) replaces the foreground-server ownership and listener-verification portions of this note; helper cleanup and task retention remain active.

[INV-SCHED-39] covers the resumed scheduler entry, not only recovery's return. [Base Scheduling](../../../../docs/subsystems/base-scheduler.md) defines future explicit task preservation and stale-plan rebuilding.

The [runtime task failure contract](../../../../docs/subsystems/base-scheduler.md#211-runtime-task-failure) extends this preservation to exhausted staffing failures, unconfirmed group targets and unexpected product-switch results. Original task identity, remaining work and time survive failure and persistence. Unchanged observations cannot redispatch the task, introduce a timer or stop other work. Related observations and arrangement changes reopen dispatch. Waits with production, recovery, training or dependency evidence retain their deadlines and bounds.

Interrupted trade-order insertion immediately converts to original-roster restoration in the same task at its original time. The insertion failure does not suspend this different compensation work. Restoration failure itself requires relevant new information before retrying, under the same failure-preservation rule.

Reopened failed tasks retain their stale-cleanup exemption through persistence until the remaining execution completes. Removing the dispatch failure marker cannot consume the retained work at the next fifteen-minute cleanup boundary.

Planner rebuilding and release merging preserve the same retained execution rather than replacing it with an unmarked task. Existing resource reservations exclude duplicate ordinary targets while independent personal-limit releases keep their deadlines. A persisted room observation revision supplies recovery evidence for confirmed empty rooms, which have no occupant sampling timestamp. The existing readback and state persistence paths own this evidence; no retry timer or separate observation loop is added.

Name-recognition failure preserves unconfirmed occupancy and bed state in both ordinary and rescue readback; it never supplies synthetic absence evidence to a failure snapshot. Existence queries explicitly include failed tasks while dispatch excludes them. Deduplication covers trade insertion before roster capture and the other existing generation callers, retaining the original task without suppressing unrelated work.

## Simplification

The existing shutdown gate distinguishes final release from normal idle cleanup. The existing scheduler cleanup predicate retains future explicit work; critical-appointment and ordinary-plan rules remain local to `handle_error`. Runtime task failures add one task-local failure snapshot in the original queue without a second queue or a separate recovery scheduler. Dispatch and idle budgets exclude unchanged failures. The snapshot compares requested and effective arrangements with related occupancy, successful observation timestamps and facility state; elapsed wall time and unrelated observations do not release it. Existing task persistence and listing retain the failure reason and original task.

The desktop OS matrix runs shared ADB application recovery, helper shutdown and scheduler preservation regressions with substituted resources, without listener ownership checks or host commands.

The task-scope repair addresses a shared cause of repeated regressions: callers treated queue membership as dispatch eligibility or permission to rewrite. The existing failure-preservation invariant now uses explicit dispatch, ordinary-replan and pending-resource scopes. One retained-resource footprint feeds matching, allocation, reordering and corrections; separating allocation from its subsequent reorder had allowed a valid bed choice to move into a retained reservation. Focused regressions traverse the production entries across paused, reopened and serialized states, and assert independent progress as well as retained task identity. The existing record owns this repair; task roles and domain concepts remain unchanged, so no glossary edit or lifecycle transition is required.

## Verification

`device_control_shutdown_tests.py` covers shutdown with live operations, deferred helper cleanup, ordered compensation and idempotent release. `device_adb_recovery_tests.py` covers same-target helper reconstruction, peer-process restart generations, cancellation, action budgets and cleanup that never closes the shared recovery coordinator.

`scheduler_recovery_preservation_tests.py` covers stale-plan boundaries, critical appointments, task payload retention, actual scheduler dispatch and the worker's recovery-to-scheduler transition.

`task_failure_retention_tests.py` covers unchanged-state repetitions, related and unrelated observations, changed targets and layouts, unchanged task times, serialization and stale cleanup, continued dispatch of independent work, ordinary planning with only a failed task, mixed product targets and preserved production waits. Room-retry and group-confirmation regressions preserve bounded local recovery and actual readback. Review follows the real worker idle selection and scheduler dispatch paths; configuration errors remain in validation and cancellation, device recovery and destructive-operation safeguards retain their existing boundaries.

Trade-order regressions exercise interrupted insertion through room-recovery and recognition failures, immediate restoration dispatch, unchanged-state suppression after restoration failure and release by a related observation. `base_scheduler_tests.py` verifies actual insertion, failed Drone Acceleration and successful original-roster restoration without replaying acceleration. The product-switch fixture in `backup_replacement_state_tests.py` uses a three-slot trading post so its state-preservation checks pass through the real trade-order validation.

Reopening regressions advance the virtual clock by twenty minutes, update a related observation and exercise the real scheduler entry. The same remaining task survives repeated cleanup alongside unrelated expired tasks and survives a serialization round trip before execution.

Planner regressions repeatedly run actual return and release planning for failed, reopened and serialized executions, verify original identity, targets and time, and admit unrelated returns. Specialized-release and merge cases preserve retained work without suppressing independent personal-limit deadlines. Empty-room cases execute ordinary and rescue readback with substituted page recognition, distinguish confirmed vacancies from failed reads and unresolved names, and verify legacy snapshot compatibility, database persistence and startup restoration of room revisions.

The review follow-up passes 1785 targeted offline tests across 35 related files, including nine added cleanup, observation and rotation cases. The [takeover decision](../simplification/2026-10-12-immediate-rescue-takeover.md) records the rescue-specific review evidence.

The worker test substitutes the active selection-card startup read and asserts that it runs once. The worker and scheduler share a virtual clock; recovery and scheduler waits advance that clock without wall-clock sleep. Retired dormitory-probe methods are absent from the fixture.

The planner and readback review regressions cover failed and reopened tasks through the actual generation paths. Occupied-room and dormitory cases distinguish unresolved names from confirmed vacancies, preserve bed and release state, and exclude prediction invalidation from successful observation evidence, including legacy snapshots. Trade-order cases fail before roster capture through both room and recognition errors, repeat planning after persistence, dispatch another room, resume the same task on relevant evidence and admit a subsequent order only after completion. Charging, exhausted-shift and idle-release cases verify the same existence-query boundary.

The latest review repair passes 2080 targeted offline tests across 41 related files, including 21 added cases, and both supplied review reproductions pass. Ruff, formatting, diff checks and all three governance gates pass; the focused run retains two existing Pydantic serializer warnings.

No live device, remote configuration, Device Profile schema or glossary definition changes.

The initial combined focused scheduler regressions pass 1593 offline tests, including 13 failure-retention cases. The CI follow-up passes 507 targeted tests across task retention, backup staffing, scheduler entry, run-order restoration, emergency compensation and maintenance orders, including two added insertion-to-restoration failure cases. Ruff, format checks, `git diff --check` and repository governance pass; governance retains two historical reference warnings. The loader test retains one existing Pydantic serializer warning. Actual device operation remains unverified.

The subsequent review repair passes 2397 focused offline tests across 45 files, including 47 added regressions. Ordinary patrol preserves unresolved occupancy through its real caller. Complete-cycle coalescing retains failed and reopened task objects, times and plans across repeated planning and serialization; derived corrections and bed allocation respect their reservations while unrelated work and ordinary coalescing continue. Four supplied reproductions first fail and then pass. The [takeover decision](../simplification/2026-10-12-immediate-rescue-takeover.md) records the restored training protection.

The task-scope consolidation passes 2869 focused offline tests across 62 files, including 102 lifecycle cases. The first 100 new cases produce 94 failures and six controls passing at the prior head, then all pass after the repair. Tests cover retained fill preflight, paused-task precedence, backup coalescing, charging and order timing refresh, reopened remaining work, partial-group admission, source and destination reservations, subsequent dormitory reordering, and rescue release planning through persistence. The supplied review reproductions also pass. Ruff, formatting, diff and governance checks pass; governance retains two historical reference warnings and behavior tests retain two existing Pydantic warnings. Actual device operation remains unverified.

The CI interface follow-up preserves lightweight dormitory reservations that predate retained-execution state. An absent retention attribute denotes an ordinary reservation; it does not expand a personal-limit reservation to the whole group. Both previously failing strict-reservation cases pass, and the focused set expands to 2902 passing tests across 63 files with the same two existing Pydantic warnings.
