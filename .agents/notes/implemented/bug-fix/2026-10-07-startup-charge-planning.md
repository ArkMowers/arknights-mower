---
title: Startup Charge Planning
status: implemented
category: bug-fix
date: 2026-10-07
---

# Startup Charge Planning

## Contract

Completed initial Fiammetta charging and original-roster restoration enqueue an immediate normal planning pass. Pending restoration retains startup priority; critical tasks retain their operation windows and all other queued tasks remain present.

## Cause and implementation

Charging calls `skip`, which marks normal planning complete. Removing the final initial charging task leaves that marker set, so the empty-queue fallback schedules a check two and a half hours later. The completed-task boundary creates one immediate empty task only after the last initial charging or restoration task leaves the queue. The next scheduler entry applies current backup conditions and normal planning. A deferred restoration does not create an early followup.

## Verification

The offline replay exercises initial admission, target selection, charging and original-roster restoration using real scheduler methods and simulated room I/O. It verifies immediate normal planning, future-task preservation, restoration deferral and critical-task precedence.
