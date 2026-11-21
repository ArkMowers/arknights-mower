---
title: Backup Product Rest State
status: implemented
category: simplification
date: 2026-10-06
---

# Backup Product Rest State

[INV-SCHED-28]

Product changes reuse the replacement transition boundary without requiring equal old and new products. Its two callers cover independent backup transitions and shift projection. The existing replacement matcher prioritizes a maximum matching of available covers before adding eligible primary recalls; no separate product staffing planner or mode is added.

Unchanged primaries, facility types and ordered group bindings retain working or resting state while replacements are available. A shortage permits the affected primary to return early from rest. Recall respects task and product reservations, mastery protection, occupied recovery positions and other working assignments. Ordinary return tasks are rebuilt after recall; locked product shifts remain reserved. Existing group correction retains consistent group staffing after an early recall. Explicit staffing tasks retain priority. Failed admission preserves active conditions and queued staffing tasks. Product observation and switching retain their existing execution boundary.

## Verification

Offline tests cover manufacturing and trading product entry and exit, working and resting primaries, complete cover matching before recall, protected recalls, recovery ownership, explicit tasks and full shift convergence.
