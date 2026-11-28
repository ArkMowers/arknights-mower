---
title: Trade Order Admission Time Budget
status: implemented
category: bug-fix
date: 2026-10-08
---

# Trade Order Admission Time Budget

## Contract

[INV-SCHED-36] counts queued work once and includes waiting, order insertion and restoration. Ordinary staffing tasks retain an executable prefix. A workshop batch before the same order admits in full or defers in full, including intervening operations and future waiting in its budget. Fully observed independent room components split; cross-room moves, all configured group bindings, unknown occupants, backup plans and task phase state retain atomic plans. Deferred work remains in the queue for subsequent orders.

## Timing Evidence

Read-only analysis of alexsun logs from 2026-10-06 through 2026-10-08 includes 170 completed ordinary tasks and 734 room operations, including recoverable navigation retries and errors. Changed dormitories have P95 67.73 seconds; changed work facilities have P95 43.12 seconds. Ordinary work uses 45 seconds per changed facility, 15 seconds for observed unchanged work and 10 seconds per task. Successful work-room measurements raise the changed-room budget to the recent maximum times 1.2 plus 15 seconds; each room retains at most eight samples. Dormitories retain the existing 90-second minimum, recent maximum times 1.2 plus 15 seconds, and the one-minute critical margin. Strict mood release and mastery protection retain their current contracts. No raw instance logs enter the repository.

## Simplification

The scheduler reuses `Operators.project_arrangements` and operation timing. Dynamic arrangements invalidate subsequent admission projections. Existing glossary terms cover Actual and Projected Occupancy and Scheduling Plan; no glossary edits are required.

The unified cursor initially removes the previous ordinary-work deferral horizon. Rebuilt future dormitory releases repeatedly produce INFO messages whose available budget refers to a future start rather than the current time. The [critical task admission contract](../../../../docs/subsystems/base-scheduler.md#210-critical-task-admission) separates future planning from due-work admission, retaining the full operation-budget protection for work that can start now. Existing domain concepts remain unchanged.

Future dormitory deferral appends each conflicting task after the last dormitory task deferred for that order, using the existing admission queue. The last-task references exist only within one admission pass and are bounded by the queued order count. This preserves successive arrangements of the same slot without adding task phase state or another scheduling abstraction.

Advance dormitory deferral uses the existing arrangement resource extraction and observed occupancy to retain dependent followups in the same queue segment. Target and displaced operators, changed slots and all configured group bindings connect later arrangements transitively. Unknown occupancy or task phase state retains the unproven suffix; unchanged ordinary plans remain independent. Release target and original-start metadata retain their existing identity meaning. Protected followups keep the original segment in place for normal admission. The helper adds no dependency graph or persistent task fields.

## Verification

Focused offline tests cover timing boundaries, independent partial plans, phase and group atomicity, isolated projection, future waiting, order occupancy, multiple orders, strict release, mastery handoffs and dorm continuation.

The workshop queue regression uses a fixed clock and checks all eleven one-minute jobs deferred after an eight-minute trade order. Repeated planning preserves all eleven task identities, operator names, order and timestamps without duplicate batches. Batch boundary tests cover scheduled waiting, intervening staffing, retained staffing prefixes and repeated deferral across later orders.

Future-work regressions cover the ten-minute boundary at both scheduling entry points, complete workshop batches, repeated dormitory release reconstruction with no INFO output or unrelated work deferral, unchanged mastery protection, and INFO output for due deferral and runtime dormitory rechecks. The existing distant-order regression retains protection for large due arrangements.

Dormitory-order regressions cover three successive arrangements of the same slot, equal and distinct original timestamps, both scheduling entry points, repeated planning, the ten-minute boundary, deferral across later orders and arrangements already queued after the order. They preserve task identities, plans and the last specified occupant while independent work retains its original time.

The dormitory-order repair passes twelve focused offline suites with 323 tests and 38 subtests, including governance verification. Changed-file Ruff lint and format checks, whitespace checks and the governance gate pass; the gate retains two historical archived-test reference warnings.

Dependency regressions verify that dormitory admission followed by the same operator's return leaves that operator at the workstation, with and without observed occupancy, after repeated planning and at the ten-minute boundary. Additional cases cover displaced residents, group bindings, transitive slot reuse, unknown residents, task phase state, dynamic Free selection, protected followups and unchanged plans. The independent-release forecast uses observed staffing to establish independence.

The dependency repair passes thirteen focused offline suites with 367 tests and 38 subtests. The 22 added dependency and fallback cases extend the same invariant without changing glossary definitions. Changed-file Ruff lint and format checks, whitespace checks and all three governance gates pass.

## Standards Findings

Pass: bounded timing samples, existing projection isolation and protected task state remain intact. The invariant appears in all three governance references.

## Spec Findings

Pass: the initial 17 focused offline suites pass 631 tests and 21 subtests; workshop batch admission and related follow-up suites pass 182 tests and 21 subtests. Ruff lint, changed-file format, whitespace and all documentation governance gates pass. Admission preserves executable work and queues the dependent remainder without repeated duration accumulation or task loss. Estimates are conservative operational budgets, not upper bounds on arbitrary future stalls.
