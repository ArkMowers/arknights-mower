---
title: Maintenance Backup Ordering
status: implemented
category: feature
date: 2026-09-30
---

# Maintenance Backup Ordering

[English](2026-09-30-maintenance-backup-ordering.md) | [中文](2026-09-30-maintenance-backup-ordering.zh.md)

## Contract

The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns **[INV-SCHED-11] Maintenance Backup Ordering**. The [coding standards](../../../../CODING_STANDARDS.md) and [review checklist](../../../skills/mower-code-review/references/invariants-checklist.md) register the same guarantee.

## Implementation

The maintenance row edits an existing comparison with a default threshold of half an hour. `Operators.next_major_maintenance_check` supplies only future threshold deadlines. The condition becomes false at downtime start; the existing major-update flow saves state and stops the automation thread. The first normal backup check after task restart exits the backup, without an exit shift during downtime. The [cutoff and evaluation correction](../bug-fix/2026-09-30-maintenance-cutoff-condition-evaluation.md) defines the boundary tests. One empty scheduler task wakes normal backup convergence; it carries no new persistent configuration.

Entry advances only the existing pre-maintenance order batch through `adjust_run_order_for_maintenance`. Tasks retain the Drone Acceleration flag and their retry times; queued roster restoration inherits the batch marker. Backup switching waits until the batch completes. New run-order creation pauses during entry.

`swap_plan` tracks which effective primary slots originate from maintenance backups. Explicit later assignments replace permission, while `Current` preserves it. Ordinary primary/replacement validation remains effective. The existing run-order room filter and queue synchronization pause all trading posts when a permitted primary remains, preserve unrelated tasks, and resume orders after exit.

The maintenance condition has a contextual question-mark description using `HelpText`. Existing conditions preserve their stored thresholds. The user-approved glossary addition records maintenance backups in terms of Scheduling Plan, Dynamic Shift Transition, and Drone Acceleration; persistent configuration schemas remain unchanged.

## Verification

Hermetic tests cover every trade order agent, nested and literal conditions, slot precedence, replacements, all-room suppression, unrelated task preservation, deadline deduplication, exit checks, entry sequencing, retry delays, and roster restoration. Existing order-product, backup-condition, rescue-condition, and scheduler tests verify adjacent behavior. Frontend tests cover the half-hour default and compatibility with existing comparisons.
