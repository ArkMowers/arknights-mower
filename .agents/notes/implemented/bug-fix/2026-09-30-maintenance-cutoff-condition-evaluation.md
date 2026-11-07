---
title: Maintenance Cutoff and Condition Evaluation
status: implemented
category: bug-fix
date: 2026-09-30
---

# Maintenance Cutoff and Condition Evaluation

[English](2026-09-30-maintenance-cutoff-condition-evaluation.md) | [中文](2026-09-30-maintenance-cutoff-condition-evaluation.zh.md)

## Contract

The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns **[INV-SCHED-11] Maintenance Backup Ordering**. The maintenance condition is false from announced downtime start, including with a cached announcement. Major downtime stops the automation thread; the first backup check after task restart exits the saved maintenance backup.

## Implementation

`Operators.major_maintenance_remaining_hours` returns infinity for started maintenance, preserving the saved finite `<= hours` comparison. `next_major_maintenance_check` supplies only future threshold wakeups. No announcement-end check or exit arrangement runs during downtime.

`BaseSchedulerSolver.backup_plan_solver` reuses its initial condition results for the first convergence pass. It evaluates again only after a plan swap changes projected state. The maintenance-entry guard consumes the same initial results; subsequent passes retain ordering and rollback checks. This removes duplicate evaluation when the plan is unchanged without adding another evaluator or cache.

## Verification

Hermetic tests check one microsecond before start, exact start, cached maintenance during downtime, and exit after restart. Existing initial-mood tests assert one condition evaluation against original residents and newly read mood. Backup convergence, order-product, and scheduler tests cover adjacent behavior.
