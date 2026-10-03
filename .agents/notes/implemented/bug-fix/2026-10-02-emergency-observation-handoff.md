---
title: Intelligent Rescue Observation and Handoff
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Observation and Handoff

## Contract

[INV-SCHED-09] binds intelligent rescue exit to actual measured recovery targets and feasible native rotation. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) defines the room-read and task-context guarantees.

Room readback captures the operators present before the read. Every absent operator loses its measured timestamp, even when the reader already clears its position. An operator without a valid measured timestamp cannot establish target completion.

The handoff arrangement owns a dedicated ordinary `SchedulerTask` during `agent_arrange`. The previous task is restored before room readback and final scheduling, including after deferral and errors. Arrangement does not inherit the mood-check task or specialized task flags, and retained arrangements continue through the existing handoff plan.

## Simplification

The change stays inside the existing room-read and staffing-restoration boundaries. One pre-read snapshot retains the observation identity, and one local task scope supplies the context required by ordinary scheduling. No additional task-context abstraction or generalized missing-task guard is introduced.

## Verification

`automatic_rescue_tests.py` covers restoration with no active task and with a mood-check or Fiammetta task, task-context compensation on success, deferral and exceptions, and reader-cleared absent occupants. `resting_priority_tests.py` exercises an actual intelligent rescue episode with opened beds, pending dormitory reservations and the last available bed; admission preserves configured primary and replacement priority. All device operations use test doubles.

The existing glossary definition already requires measured targets and unified staffing restoration; no glossary edits are needed.

## Review

Standards Findings: the change uses a pre-read occupant snapshot and a local task compensation boundary. Production scheduling guards remain intact, and retired test attributes are removed.

Spec Findings: real arrangement and room-read entry points cover missing task context and reader-cleared positions. Actual recovery bed planning retains configured operator priorities and reservations. The seven focused offline suites pass 270 tests and 4 subtests.
