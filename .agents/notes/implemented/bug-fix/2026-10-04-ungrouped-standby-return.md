---
title: Ungrouped Standby Return
status: implemented
category: bug-fix
date: 2026-10-04
---

# Ungrouped Standby Return

## Contract

[INV-SCHED-19] binds an ungrouped standby primary to the earliest eligible ordinary shift-on batch. The primary has no current room, its native slot contains a configured replacement, and a required primary provides a recovery anchor. Full mood does not require a personal mood-limit setting for this return. Grouped standby primaries retain group-owned return timing.

Return planning preserves task deadlines, actual occupancy, bed ownership, busy operators, pending arrangement ordering and product reservations. Release-only batches do not recall standby primaries. No eligible ordinary batch means no independent standby return task.

## Simplification

The existing `plan_metadata` rebuild, `is_standby` predicate and native-slot assignment provide the return path without persistent standby state, a new task type or another correction rule. Configured replacement order and exhausted replacement handling remain unchanged. The [priority-aware recovery contract](../../implemented/simplification/2026-10-02-priority-aware-dorm-recovery.md) retains bed admission and displacement ownership.

## Verification

`group_resting_capacity_tests.py` covers measured-full and partially recovered standby primaries with both exhausted and non-exhausted covers, repeat queue rebuilding, release-only batches, missing return deadlines and reservations. Existing group and replacement-correction tests preserve their behavior. All tests run without device or network I/O.
