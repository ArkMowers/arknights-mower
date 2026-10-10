---
title: Startup Charge Planning
status: implemented
category: bug-fix
date: 2026-10-07
---

# Startup Charge Planning

## Contract

Completed initial Fiammetta charging, original-roster restoration and backup transitions resume normal planning at their completion boundary under [INV-SCHED-04]. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns ordering, retry and task-preservation rules.

## Cause and implementation

Charging calls `skip`, which marks normal planning complete. Removing the final initial charging task leaves that marker set, so the empty-queue fallback schedules a check two and a half hours later. The completed-task boundary creates one immediate empty task only after the last initial charging or restoration task leaves the queue. The next scheduler entry applies current backup conditions and normal planning. A deferred restoration does not create an early followup.

The same completion responsibility covers dormitory reorders and backup-generated corrections. A failed arrangement postpones the concrete task while its earlier empty planning task can be consumed first. Successful `RE_ORDER` execution then calls `skip`; with only future shift returns left, the outer loop can start MAA and wait without rebuilding trade orders. This existing defect reproduces on upstream baseline `4edfb1a5`; it is independent of the separate original-roster restoration repair.

Completion reuses an already due anonymous empty task or creates one. Existing task type and backup metadata identify the responsibility after restart, without a new saved-state field. Unconfirmed arrangements do not enter the completion path. [INV-06] reuses unchanged scheduling concepts; no glossary definitions change.

## Verification

The offline replay exercises initial admission, target selection, charging and original-roster restoration using real scheduler methods and simulated room I/O. It verifies immediate normal planning, future-task preservation, restoration deferral and critical-task precedence.

`run_order_planning_wakeup_tests.py` exercises real backup convergence, scheduler entry and trade-order planning with simulated device I/O. Its failure assertion checks the queue at completed retry exit, before another scheduler call can hide the missing wake. Cases cover ordinary completion, repeated deferral, saved-task continuation, future returns and existing order/restoration tasks.

The new suite passes 10 tests; a combined run with eight related offline suites passes 501 tests. The final regression also fails against the unchanged upstream scheduler loaded in memory, at the missing completion wake. SQLite persistence uses a temporary database, and device creation, network sockets, HTTP requests and external processes are forbidden in the new fixture. Scoped Ruff, formatting and whitespace checks pass; governance retains only two historical archived-reference warnings.

## Review

Standards review preserves existing completion, projection, confirmation and compensation boundaries. It corrects the contract scope and simulated room return value; concepts and the owning decision remain unchanged.

Spec review confirms normal completion, one and three deferrals, continuation in a new scheduler after persistence, planning before future returns and one dispatch per existing order/restoration task. Both review axes have no unresolved findings. Full startup restoration is traced; the focused restart test uses real persistence and restoration methods rather than running the complete automation entry point.
