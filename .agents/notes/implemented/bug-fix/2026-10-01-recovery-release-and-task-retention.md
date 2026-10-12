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

## Simplification

The existing shutdown gate distinguishes final release from normal idle cleanup. The existing scheduler cleanup predicate retains future explicit work; critical-appointment and ordinary-plan rules remain local to `handle_error`. Runtime task failures add one task-local failure snapshot in the original queue without a second queue or a separate recovery scheduler. Dispatch and idle budgets exclude unchanged failures. The snapshot compares requested and effective arrangements with related occupancy, successful observation timestamps and facility state; elapsed wall time and unrelated observations do not release it. Existing task persistence and listing retain the failure reason and original task.

The desktop OS matrix runs shared ADB application recovery, helper shutdown and scheduler preservation regressions with substituted resources, without listener ownership checks or host commands.

## Verification

`device_control_shutdown_tests.py` covers shutdown with live operations, deferred helper cleanup, ordered compensation and idempotent release. `device_adb_recovery_tests.py` covers same-target helper reconstruction, peer-process restart generations, cancellation, action budgets and cleanup that never closes the shared recovery coordinator.

`scheduler_recovery_preservation_tests.py` covers stale-plan boundaries, critical appointments, task payload retention, actual scheduler dispatch and the worker's recovery-to-scheduler transition.

`task_failure_retention_tests.py` covers unchanged-state repetitions, related and unrelated observations, changed targets and layouts, unchanged task times, serialization and stale cleanup, continued dispatch of independent work, ordinary planning with only a failed task, mixed product targets and preserved production waits. Room-retry and group-confirmation regressions preserve bounded local recovery and actual readback. Review follows the real worker idle selection and scheduler dispatch paths; configuration errors remain in validation and cancellation, device recovery and destructive-operation safeguards retain their existing boundaries.

The worker test substitutes the active selection-card startup read and asserts that it runs once. The worker and scheduler share a virtual clock; recovery and scheduler waits advance that clock without wall-clock sleep. Retired dormitory-probe methods are absent from the fixture.

No live device, remote configuration, Device Profile schema or glossary definition changes.

The combined focused scheduler regressions pass 1593 offline tests, including 13 failure-retention cases. Ruff, format checks, `git diff --check` and repository governance pass; governance retains two historical reference warnings. The loader test retains one existing Pydantic serializer warning. Actual device operation remains unverified.
