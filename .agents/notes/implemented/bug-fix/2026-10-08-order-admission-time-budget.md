---
title: Trade Order Admission Time Budget
status: implemented
category: bug-fix
date: 2026-10-08
---

# Trade Order Admission Time Budget

## Contract

[INV-SCHED-36] counts queued work once and includes waiting, order insertion and restoration. Ordinary tasks retain an executable prefix. Fully observed independent room components split; cross-room moves, all configured group bindings, unknown occupants, backup plans and task phase state retain atomic plans. Deferred work remains in the queue for subsequent orders.

## Timing Evidence

Read-only analysis of alexsun logs from 2026-10-06 through 2026-10-08 includes 170 completed ordinary tasks and 734 room operations, including recoverable navigation retries and errors. Changed dormitories have P95 67.73 seconds; changed work facilities have P95 43.12 seconds. Ordinary work uses 45 seconds per changed facility, 15 seconds for observed unchanged work and 10 seconds per task. Successful work-room measurements raise the changed-room budget to the recent maximum times 1.2 plus 15 seconds; each room retains at most eight samples. Dormitories retain the existing 90-second minimum, recent maximum times 1.2 plus 15 seconds, and the one-minute critical margin. Strict mood release and mastery protection retain their current contracts. No raw instance logs enter the repository.

## Simplification

The scheduler reuses `Operators.project_arrangements` and operation timing. Dynamic arrangements invalidate subsequent admission projections. Existing glossary terms cover Actual and Projected Occupancy and Scheduling Plan; no glossary edits are required.

## Verification

Focused offline tests cover timing boundaries, independent partial plans, phase and group atomicity, isolated projection, future waiting, order occupancy, multiple orders, strict release, mastery handoffs and dorm continuation.

## Standards Findings

Pass: bounded timing samples, existing projection isolation and protected task state remain intact. The invariant appears in all three governance references.

## Spec Findings

Pass: 17 focused offline suites pass 631 tests and 21 subtests. Ruff lint, changed-file format, whitespace and all documentation governance gates pass. Admission preserves executable work and queues the dependent remainder without repeated duration accumulation or task loss. Estimates are conservative operational budgets, not upper bounds on arbitrary future stalls.
