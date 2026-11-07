---
title: Rescue Selection Page Restoration
status: archived
category: bug-fix
date: 2026-10-03
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# Rescue Selection Page Restoration

## Contract

[INV-SCHED-09] requires temporary-worker scanning to refresh the facility product before opening resident details and entering selection. Product inspection can close resident details. Scanning always returns to infrastructure on success or failure.

## Simplification

The scan uses the same ordering as normal room readback and reuses `turn_on_room_detail`. Initial staffing and combination rescoring share this scan. No new helper, retry policy, cache or configuration is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the rule.

## Verification

A stateful offline page model closes resident details during manufacturing and trading product refresh. Both cases reproduce the selection-entry error before the fix; control-center scanning provides a no-product control. Existing recognition-failure coverage checks cleanup.

## Review

Standards Findings: PASS. The change reuses existing bounded navigation and preserves cleanup and device ownership. Ruff and diff checks pass.

Spec Findings: PASS. Manufacturing and trading scans restore resident details after product inspection; control-center scanning remains valid. Focused offline tests pass: 157 tests and 4 subtests. No live-device integration runs are used.
