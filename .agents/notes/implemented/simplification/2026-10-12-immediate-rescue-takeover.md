---
title: Immediate Rescue Takeover
status: implemented
category: simplification
date: 2026-10-12
---

# Immediate Rescue Takeover

## Contract

[INV-SCHED-09] gives an admitted rescue schedule immediate authority over configured working positions. Unknown mood, reservations and queued compensation do not postpone takeover. Training protection remains binding: busy or protected training rooms skip both slots, and their occupants remain unavailable to other rooms. Unreadable live training state also skips the room. Attempted but unreliable slot reads retain this protection even when the main panel appears empty. Skipping removes those positions from completion without a delayed task or repeated staffing attempt; other rooms continue. Empty unprotected training rooms retain normal deployment. Actual occupancy determines completion and unfinished rooms after a device or recognition failure. [INV-SCHED-03] retains recovery release rules after takeover; queued releases do not preempt takeover.

The episode persists initial takeover completion independently of later staffing rounds. An incomplete initial takeover retains priority after restart; subsequent worker rotations follow personal-limit release protection. Retained staffing failures leave the existing recovery observation cycle and independent release planning available under the [runtime failure contract](../../../../docs/subsystems/base-scheduler.md#211-runtime-task-failure).

## Simplification

The scheduler removes mood, reservation and compensation deferrals from rescue deployment. One persisted task owns the executable roster and dispatches before other queued tasks. Work-room restoration snapshots adopt only confirmed takeover occupants through the shared room-observation boundary or confirmed staffing reconciliation; planned but skipped occupants never replace the original restoration responsibility. The shared training filter and live arrangement gate retain training protection. A source-training check prevents indirect removal through another room's staffing. Skipped targets use the existing Current placeholder for reconciliation instead of another queue or retry timer. The existing arrangement executor owns confirmed input and bounded recovery.

## Verification

The latest review repair passes 2397 targeted offline tests across 45 related files, including 47 added regressions across task preservation, ordinary patrol and training protection. Training cases cover automatic mastery and assistant-follow settings, busy and unreadable rooms, empty-room deployment, continued independent staffing, skipped-target reconciliation, source-training protection and unchanged-state suppression. The four supplied task-retention reproductions pass after first confirming their failures.

Ruff checks, format checks, `git diff --check` and all three governance gates pass. Governance retains two historical reference warnings; the focused tests retain two existing Pydantic serializer warnings. Live-device execution remains unverified.

The existing Scheduling Plan, Actual and Projected Occupancy, and Rescue Recovery concepts remain unchanged. This repair changes execution protection and preserves the existing glossary definitions; no glossary edit or note lifecycle transition is required.

The shared-boundary refactor passes 2048 focused offline tests across 41 repository files, plus all six supplied review reproductions. The same six reproductions fail at the previous commit `60e9861922b550e828730e1aa6d26ecbd4874853`. Cases verify partial work-room and dormitory observations through ordinary, patrol and rescue readers; paused and reopened order retention; priority and runtime dormitory yielding without timestamp changes; unreliable training slots; and compensation snapshots across skipped targets, confirmed readback and serialization. The run retains eight existing Pydantic warnings. The English and Chinese glossary definitions of Actual and Projected Occupancy, Dynamic Shift Transition, Dormitory Recovery and mandatory releases were checked; their meanings remain unchanged.
