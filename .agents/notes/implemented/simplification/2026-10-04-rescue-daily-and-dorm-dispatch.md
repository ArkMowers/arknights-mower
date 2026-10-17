---
title: Rescue daily and dormitory dispatch
status: implemented
category: simplification
date: 2026-10-04
---

# Rescue daily and dormitory dispatch

## Contract

Daily work retains ordinary time budgets during automatic rescue. Clues, drones and replenishment remain enabled. Normal backup transitions and ordinary shift correction remain frozen. Rescue workers and specialized tasks retain existing reservations and compensation.

## Simplification and implementation

Three blanket rescue guards block the shared daily loop, MAA eligibility and infrastructure chores. Removing those guards reuses ordinary task selection and deadlines without a parallel daily scheduler. MAA daily dispatch contains startup, fighting, mall and rewards; it does not dispatch infrastructure staffing.

Recovery release projects its post-departure occupants, reuses the bed opener and bed planner, and executes the final combined arrangement within the strict-release budget. Pending dormitory tasks retain their existing ownership. Normal full-recovery configuration fixes recovery targets at personal caps and applies to handoff verification.

## Review and verification

[INV-SCHED-03] retains measured ownership and strict release windows. [INV-SCHED-09] retains full-recovery requirements and ordinary daily scheduling. Offline regressions exercise the real main loop and infrastructure branch, MAA eligibility and short-window deferral, combined release/fill, and full-rest targets and handoff. Standards review checks projection isolation and compensation; specification review checks allowed daily operations, frozen normal shifts and measured recovery.

Validation: 444 focused tests and 24 subtests pass. Ruff and whitespace checks pass. No live emulator integration runs.
