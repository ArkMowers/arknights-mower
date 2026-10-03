---
title: Rescue Staffing Before Observation
status: implemented
category: bug-fix
date: 2026-10-03
---

# Rescue Staffing Before Observation

## Contract

[INV-SCHED-09] consumes initial measured observations directly for staffing planning, without collection or repeat room reads. Pending rescue staffing precedes due recovery observation and additional workshop/order planning; strict release tasks remain in the scheduler. Routine observation reads only dormitories containing recovery primaries whose measured targets remain unconfirmed. Explicit unfinished initialization and final-handoff observations retain their remaining-room checkpoints.

## Simplification

The existing observation marker and queued staffing flags determine ordering. No new phase, cache, timer or compatibility path is added. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns this rule.

## Verification

Offline regressions cover initial direct dispatch, pending staffing priority, restricted dormitory scope, collection on regular checks, and strict-release interruption/resumption of explicit full reconciliation.

## Review

Standards Findings: PASS. Existing task identity, readback checkpoints and strict release priorities remain intact; no new persistent fields are added.

Spec Findings: PASS. Focused offline suites pass 520 tests and 24 subtests. Initial observations bypass collection, queued staffing blocks repeat observation, and normal reads exclude working facilities. Initialization and handoff checkpoint coverage remains explicit. Ruff and governance checks pass; no live-device integration runs are used.
