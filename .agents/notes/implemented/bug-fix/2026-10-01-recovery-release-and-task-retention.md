---
title: Recovery Release and Task Retention
status: implemented
category: bug-fix
date: 2026-10-01
---

# Recovery Release and Task Retention

## Contract

[INV-DEV-19] covers process shutdown with an active run context and deferred helper cleanup. [Device Control](../../../../docs/subsystems/device-control.md) defines release ordering and idle ownership.

[INV-SCHED-13] covers the resumed scheduler entry, not only recovery's return. [Base Scheduling](../../../../docs/subsystems/base-scheduler.md) defines future explicit task preservation and stale-plan rebuilding.

## Simplification

The existing shutdown gate distinguishes final release from normal idle cleanup. The existing scheduler cleanup predicate retains future explicit work without adding task provenance fields, a second queue or a separate recovery scheduler. Existing critical-appointment and ordinary-plan rules remain local to `handle_error`.

Linux listener tests substitute both platform selectors, the process socket table and descriptor links. They reject host commands and require no filesystem symlink privileges. The desktop OS matrix runs owned ADB and scheduler preservation regressions.

## Verification

`adb_owned_server_tests.py` covers active-run shutdown, deferred cleanup, idempotent release and idle ownership. Its listener test validates matching and mismatched socket inodes using only substituted resources.

`scheduler_recovery_preservation_tests.py` covers stale-plan boundaries, critical appointments, task payload retention, actual scheduler dispatch and the worker's recovery-to-scheduler transition. The existing transport tests retain shared-server and same-target routing coverage.

No live device, remote configuration, Device Profile schema or glossary definition changes.
