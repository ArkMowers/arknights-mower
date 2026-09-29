---
title: Complete shift convergence
status: implemented
category: simplification
date: 2026-09-29
---

# Complete shift convergence

## Contract

Experimental Dynamic Shift Transition converges backup conditions, eligible off-shift groups, cached corrections, and final empty-bed filling before submitting one arrangement. The planner reuses `resting`, `try_reorder`, `_prepare_shift_backup`, and `try_add_release_dorm`; it does not introduce another candidate policy. Work-post relocation does not count as a return from rest. Actual returning operators and their groups do not immediately rotate off again in the same cycle.

[INV-SCHED-05] Complete Shift Projection requires both backup conditions and the resulting roster to stabilize. A repeated state or the iteration bound raises `ValueError` before committing the task or actual occupancy. Initial mood probes, Fiammetta charging, product-switch reservations, and urgent trade/mastery deadlines retain their existing dispatch boundaries. Unknown game-selected `Free` occupants are resolved during actual selection and require a later evaluation with that new information.

Fiammetta's temporary dorm transitions preserve the measured work depletion rate while normal mood sampling updates the mood and timestamp. Subsequent work inspections continue calibrating the rate under [INV-SCHED-01].

## Simplification evidence

`infra_main` submits ordinary shift arrangements and `run` checks empty beds. Previously these callers planned backup transitions and empty-bed filling independently of the next `resting` pass. Both now use `_prepare_shift_cycle`; candidate ranking, bed priority, and replacement eligibility retain their existing implementations. Backup dorm migration compares against the proposed slot changes, so an unchanged original occupant cannot be silently overwritten by an intermediate assignment.

## Verification

`shift_cycle_convergence_tests.py` covers return-triggered rotation, cache isolation, failure rollback, urgent-task protection, and a six-backup Scheduling Plan with a recorded cache and later return intent. That fixture reconstructs a planning scenario; it is not a complete device replay. Existing backup replay and dorm suites cover final-post legality and bed preservation. Charge-return reading tests cover depletion-rate retention.
