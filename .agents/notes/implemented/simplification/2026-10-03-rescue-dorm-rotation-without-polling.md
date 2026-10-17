---
title: Rescue Dormitory Rotation Without Polling
status: implemented
category: simplification
date: 2026-10-03
---

# Rescue Dormitory Rotation Without Polling

## Contract

[INV-SCHED-09] retains measured release and final handoff. [INV-SCHED-15] prevents estimates from proving release eligibility. Intelligent rescue passes its recovery targets to the existing mood-limit release planner. Measured bed countdowns schedule RELEASE_DORM tasks; configured personal limits retain their mandatory releases. Execution reconciles actual residents and mood before release and replans unfinished recovery. Ordinary observations retain operator refresh intervals; absent timing creates no independent mood-check task. Interrupted physical operations retain one continuation.

## Simplification

The empty periodic check and its five-to-thirty-minute loop are removed. No separate rescue rotation planner or bed-change algorithm is introduced. Standby and pending-release reservations derive from episode state instead of an artificial task. Normal query and rotation wakeups share collection. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns the lifecycle definition.

## Verification

Offline tests cover estimated target scheduling, insufficient measured mood, stale occupants, absent recovery timing, reservations without a task, interrupted operations and task presentation. No live-device integration is used.

## Review

Standards Findings: PASS. Existing scheduling invariants, configured personal limits, measured release and final handoff remain enforced. Formatting, lint and governance checks pass.

Spec Findings: PASS. Focused offline suites pass 977 tests and 24 subtests; frontend log and store suites pass 13 tests. Regression coverage includes personal upper-limit priority, unchanged lower/upper settings, stale occupant identity, insufficient measured mood and reservations without a polling task.
