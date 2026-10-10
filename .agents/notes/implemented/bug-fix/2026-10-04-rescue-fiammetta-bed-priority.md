---
title: Rescue Fiammetta bed priority
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue Fiammetta bed priority

## Contract

Normal primaries awaiting recovery beds displace Fiammetta. Spare capacity restores her configured rescue position before group and single-target managers. Charging-target completion is not a prerequisite. Unfinished recovering residents retain their beds.

## Implementation and simplification

The existing bed opener and shared dormitory planner own this policy; no separate queue or recovery model is introduced. Effective fixed positions gate charging wakeups. Concrete charging and pending dormitory arrangements finish before changing bed ownership. Fiammetta is excluded from ordinary fillers.

## Verification and review

Existing [INV-SCHED-03] and [INV-SCHED-09] cover bed ownership and episode recovery. Focused offline tests cover yielding the actual planned bed, return priority with tight capacity, task completion guards and charging filters. Standards review checks reservation and compensation preservation; specification review checks primary-first admission and configured return position.

Validation: 289 focused tests and 4 subtests pass. Governance, Ruff and whitespace checks pass. No live-device integration runs.
