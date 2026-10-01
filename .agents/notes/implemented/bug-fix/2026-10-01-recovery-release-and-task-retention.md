---
title: Recovery Release and Task Retention
status: implemented
category: bug-fix
date: 2026-10-01
---

# Recovery Release and Task Retention

## Contract

[INV-DEV-19] leaves the shared ADB server running during process shutdown and idle cleanup. [Device Control](../../../../docs/subsystems/device-control.md) defines application-owned helper release, deferred cleanup and idempotent closure. The [shared ADB recovery decision](../../implemented/simplification/2026-10-01-shared-adb-recovery.md) replaces the foreground-server ownership and listener-verification portions of this note; helper cleanup and task retention remain active.

[INV-SCHED-13] covers the resumed scheduler entry, not only recovery's return. [Base Scheduling](../../../../docs/subsystems/base-scheduler.md) defines future explicit task preservation and stale-plan rebuilding.

## Simplification

The existing shutdown gate distinguishes final release from normal idle cleanup. The existing scheduler cleanup predicate retains future explicit work without adding task provenance fields, a second queue or a separate recovery scheduler. Existing critical-appointment and ordinary-plan rules remain local to `handle_error`.

The desktop OS matrix runs shared ADB application recovery, helper shutdown and scheduler preservation regressions with substituted resources, without listener ownership checks or host commands.

## Verification

`device_control_shutdown_tests.py` covers shutdown with live operations, deferred helper cleanup, ordered compensation and idempotent release. `device_adb_recovery_tests.py` covers same-target helper reconstruction, peer-process restart generations, cancellation, action budgets and cleanup that never closes the shared recovery coordinator.

`scheduler_recovery_preservation_tests.py` covers stale-plan boundaries, critical appointments, task payload retention, actual scheduler dispatch and the worker's recovery-to-scheduler transition.

No live device, remote configuration, Device Profile schema or glossary definition changes.
