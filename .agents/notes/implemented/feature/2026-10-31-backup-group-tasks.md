---
format: decision
title: Backup tasks request complete group shifts
status: implemented
category: feature
date: 2026-10-31
---

# Backup tasks request complete group shifts

## Problem

Room-specific backup tasks name covers without expressing the requested group operation. A return can then project another backup entry and produce repeated dormitory migration. Group requests must reuse the [Base Scheduling Contract](../../../../docs/subsystems/base-scheduler.md), which owns matching, recovery protection and retained failures.

## Decision

The Scheduling Plan stores `group_tasks` independently from room tasks. Each entry names an existing operator group, an `on` or `off` action, and an execution mode. `once` issues one request per activation. `while_active` keeps an off-duty preference until deactivation; `forced` keeps the off-duty state and its occupied covers unavailable to other groups; on-duty requests execute once so the configuration cannot prohibit necessary recovery.

Group requests use the existing group departure and dependency-coordination paths. An off-duty preference suppresses derived ordinary returns, but allows a supported return needed by another group. A coordinated group can rest again when its dependency permits it. Explicit full recovery, protected facilities, started arrangements and recovery ownership remain binding. Failed requests retain identity and timestamp, yield dispatch, and resume only on relevant observations or dependency changes. Deactivation removes unstarted requests and the preference, then restores ordinary recovery-based returns without a forced recall.

The task dialog edits group requests separately from room occupants. Native scheduling, offline simulation, JSON transfer and validation share this representation. Existing Scheduling Plan and backup selection definitions remain unchanged.

## Alternatives considered

Enumerating covers preserves the existing format but couples group intent to particular slots and repeats the observed return conflict. Renaming a group or removing its bindings changes which operators rotate together. Adding retry intervals postpones the conflict and violates the existing failure contract.

## Verification

The focused native suites pass 187 tests, covering [request lifetime and complete departure planning](../../../../arknights_mower/tests/backup_group_task_tests.py), [saved-state recovery](../../../../arknights_mower/tests/group_shift_persistence_tests.py), backup validation and urgent recalls. The frontend and scheduling suites pass 110 tests, covering the task editor, JSON transfer, real dependency dispatch, forced cover protection and ordinary return behavior. Another 234 related simulation tests pass; production build includes the income Worker.

The supplied schedule completes 744 offline hours with three warmup days and 28 sampled days after replacing the explicit cover task with a coordinated group request and retaining only Aroma's resting condition. Parameters use maximum operator growth, potential output, seed 42 and drones in room 3-3. Aroma and Mechanist have no sampled zero-morale work; Ling still has about 1.46 hours, and temporary group coverage or bed shortages remain in the diagnostics. This establishes completion for that input, not optimal yield or device behavior.

## Consequences

Writers can express whole-group intent without enumerating covers or removing bindings. Conflicting active requests and unknown groups fail validation, including unchanged room plans that would otherwise reuse a validation result. A forced hold can delay another group's departure; a coordinated hold can temporarily lose its requested off-duty state. Preserving ordinary recovery and started handoffs takes precedence over immediate completion. Existing schedules default to no group requests; advanced settings and personal-cap departure timing are unchanged. Older versions cannot execute the new requests, so removing them or restoring the prior room tasks is necessary before using those schedules there.
