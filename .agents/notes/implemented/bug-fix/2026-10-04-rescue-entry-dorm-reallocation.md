---
title: Rescue Entry Dormitory Reallocation
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue Entry Dormitory Reallocation

## Contract

[INV-SCHED-09] reconciles rescue working facilities before a single dormitory arrangement reallocates available beds. Existing residents participate in shared recovery priorities and group admission preferences [INV-SCHED-14]. Full residents without a retained manager position leave available beds. Fixed managers, Fiammetta and task reservations remain protected.

## Simplification

The existing dormitory planner accepts a one-time reallocation mode. Its isolated arrangement projection empties available beds before shared selection, instead of adding another allocator. Later recovery uses ordinary incremental filling.

## Verification

Offline tests cover old residents, full occupants, grouped priority, reserved beds, unchanged observations, retry reconciliation and release suppression before observed completion.

## Standards Findings

Projection uses the existing isolated operator snapshot. Pending arrangement state persists with the rescue episode; task creation does not certify completion. Personal mood-limit protection remains active.

## Spec Findings

One task carries all initial dormitory changes. Recovery-target releases use the observed arrangement after completion, rather than pre-arrangement recovery times.
