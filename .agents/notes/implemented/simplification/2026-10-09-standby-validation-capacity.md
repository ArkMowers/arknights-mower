---
title: Group Capacity Validation for Standby
status: implemented
category: simplification
date: 2026-10-09
---

# Group Capacity Validation for Standby

## Contract

[INV-SCHED-42] counts eligible standby workers as optional during group capacity validation when the group has a non-standby recovery member. A group containing only standby workers retains its complete bed requirement. Ordinary workers, exhausted-shift workers and workers configured for full recovery retain mandatory recovery. Fixed dormitory assignments reduce only the mandatory workers' dynamic bed demand. Every member still requires a unique replacement, and each binding and effective backup combination receives the same validation.

## Simplification

`Operators.init_and_validate` uses `Operators._can_standby`, the existing runtime eligibility predicate, and one mandatory-worker collection instead of separately counting all working members and rebuilding the same collection for fixed-position matching. The ordinary matching keeps configured preferences when capacity suffices; constrained matching prioritizes mandatory workers for fixed dormitory positions. The existing `assign_dorm_group` retains mood, anchor, reservation and actual occupancy checks. No runtime recovery policy or configuration schema changes.

## Verification

`standby_validation_capacity_tests.py` covers eight working members with three standby workers and seven Free beds, primary and additional bindings, complete shift admission, mandatory recovery restrictions, groups containing only standby workers, unique replacements and competing fixed dormitory assignments. Related coverage remains in `group_resting_capacity_tests.py`, `same_group_dorm_replacement_tests.py`, `multi_group_shift_tests.py` and `backup_validation_tests.py`.

## Standards Findings

PASS: Shared eligibility preserves mandatory recovery restrictions and unique replacement matching. Static validation leaves runtime mood, reservations and occupancy checks unchanged. The focused scheduling and governance suites pass 304 tests and 21 subtests on alpha baseline `4edfb1a5`; the repository governance gates pass with two existing archived-reference compatibility warnings. Two existing Pydantic fixture serialization warnings remain.

## Spec Findings

PASS: Eight working members with three eligible standby workers and seven Free beds validate and complete shift projection, including a standby worker's additional binding. Ordinary, exhausted, full-recovery and all-standby groups still reject insufficient beds. Fixed standby assignments do not reduce mandatory demand; constrained fixed matching prefers mandatory workers. Backup full-recovery settings reapply the same capacity boundary without mutating the caller's active plan.
