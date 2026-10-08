---
title: Deferred Exhausted Shift Duplication
status: implemented
category: bug-fix
date: 2026-10-08
---

# Deferred Exhausted Shift Duplication

## Scope

This record captures a reproducible defect on baseline `87b9d3aa` and its repair against `31709700`. The relevant contracts are [INV-SCHED-04], [INV-SCHED-05], [INV-SCHED-10] and [INV-SCHED-38] in [Coding Standards](../../../../CODING_STANDARDS.md).

## Evidence

The October 8 runtime repeatedly generates 歌蕾蒂娅's exhausted-shift deadline, reports an unfinished off-shift task, and defers a new concrete arrangement until after the next trade order run. At `11:03:58`, the log records 45 queued SHIFT_OFF tasks. The [log excerpt](../../../../arknights_mower/tests/fixtures/deferred_exhaust_20261008.json) retains source filenames, line numbers and queue counts. It does not contain the full 45-task queue or transport and account logs.

The minimal offline scenario contains one exhausted operator, one working facility, one dormitory and one future RUN_ORDER. Three planning/dispatch rounds increase the concrete off-shift queue from one task to four. All four remain scheduled at the same deferred time.

## Cause

[`run_order_solver`](../../../../arknights_mower/solvers/base_schedule.py) checks only EXHAUST_OFF deadlines for the named operator. `overtake_room` converts a due deadline into a concrete SHIFT_OFF arrangement, and `infra_main` removes the consumed deadline. Actual and Projected Occupancy remain separate: deferral leaves the operator working in the actual cache. The next planning pass therefore creates another deadline despite the existing concrete off-shift task.

[`_schedule_run_orders`](../../../../arknights_mower/utils/scheduler_task.py) passes only the slice before the next RUN_ORDER to `_merge_deferred_dorm_schedules`. An earlier copy already scheduled after that order is outside the slice. The merge message also appears for a single SHIFT_OFF dormitory arrangement, so it does not establish that queue duplication is removed.

## Correction Contract

[INV-SCHED-38] Exhausted-shift generation and dispatch recognize one complete pending SHIFT_OFF arrangement across the whole queue, including future deferred tasks. Every recovery-requiring working member is explicitly assigned to a dormitory or remains in an unchanged actual rest position. Configured dormitory members, workaholics and shared multi-group primaries retain the existing exhausted-group completion exclusions. A member assigned to work or removed from its current bed does not satisfy coverage.

Incomplete groups and independent groups remain eligible for exhausted-shift generation. SHIFT_ON, explicit backup staffing, Fiammetta charging, specialized compensation and strict mood-limit releases do not establish an off-shift recovery arrangement. Consumption or cancellation of the concrete task reopens admission. This check preserves actual occupancy, working-facility arrangements, task identity and trade order times without changing deferred batch merging.

Coverage derives directly from current task plans through `_has_pending_exhausted_shift`; no separate recovery marker or occupancy mutation accompanies admission.

Existing duplicate concrete tasks remain in the queue and execute through normal dispatch. This repair prevents additional copies and consumes a redundant dynamic deadline without adding another concrete arrangement; it does not retrospectively combine stored tasks whose staffing or compensation responsibilities can differ.

## Verification

The [offline regressions](../../../../arknights_mower/tests/scheduler_incident_20261008_tests.py) exercise the real generator, exhausted-task dispatch and scheduler together. `test_postponed_exhausted_shift_is_not_generated_again` reproduces four tasks instead of one before repair. The control retaining a future EXHAUST_OFF marker passes before repair; that marker is diagnostic evidence, not a production implementation.

The [pending recovery tests](../../../../arknights_mower/tests/deferred_exhaust_dedup_tests.py) verify complete and partial groups, preserved and overwritten rest positions, independent operators, unrelated task types, shared-member exclusions, cancellation and redundant dynamic dispatch.

After repair, all twenty-four pending recovery cases and both incident exhaustion cases pass. The related exhausted replacement, backup rest schedule and working timer suites pass 156 tests. Ruff checks, formatting checks and repository governance gates pass. The incident scenarios exercise production entry points with mocked device I/O and resting-plan construction; they do not replay the full stored queue or verify game execution. Domain-concept names, meanings and occupancy boundaries remain unchanged.

```text
python -m pytest arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'exhausted' -q
python -m pytest arknights_mower/tests/deferred_exhaust_dedup_tests.py -q
```

The [group bed-preemption record](2026-10-08-group-bed-preemption-oscillation.md) captures the separate recovery interruption that can still generate opposite arrangements after duplicate-task admission is repaired.
