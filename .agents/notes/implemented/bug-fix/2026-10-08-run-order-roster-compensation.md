---
title: Run Order Roster Compensation
status: implemented
category: bug-fix
date: 2026-10-08
---

# Run Order Roster Compensation

[中文](2026-10-08-run-order-roster-compensation.zh.md)

## Decision and Rationale

The [incident analysis](../../../../docs/postmortem/2026-10-01-proviso-run-order.md) records a vacant original roster restored through `Free` selection and an earlier failed restoration whose task plan is empty. A separate static-main-roster fallback in `BaseSchedulerSolver.agent_arrange` also mixes observed workers with configured targets; it can replace a working substitute with a resting primary. Neither source establishes the actual original workers.

One task-owned observation supplies the original roster from admission through verified restoration. Removing the competing static fallback is part of this compensation repair, with no independent public interface, alternate roster resolver or configuration switch. The reduction removes one fallback branch and one competing roster source; total line reduction does not measure the lifecycle repair.

The repair extends existing [INV-SCHED-04](../../../../CODING_STANDARDS.md#2-subsystem-invariants), whose full operational rules live in the [shift compensation contract](../../../../docs/subsystems/base-scheduler.md#251-shift-compensation-and-run-order-restoration). Invalid normal originals return to ordinary correction. Incomplete insertion, local failures and saved-task reentry retain the same original roster and resume restoration only. Shared Proviso runs wait for earlier restoration. Automatic rescue retains its distinct observed-vacancy semantics.

The queue saved by `record.current_state` shares the executing task. A checkpoint during confirmation or Grandet waiting can therefore contain the pending marker with an insertion plan or empty plan. Normalizing at queue recovery, scheduler restart and arrangement entry closes these real reentry paths. Executable restoration retains critical priority while budgeting only remaining staffing work, without Grandet waiting or drone order adjustment.

Unconditional critical protection of a restoration waiting on occupied originals can postpone the source facility's correction at every retry. A later insertion waiting on that restoration can perpetuate the same dependency. Readiness derived from Actual Occupancy permits prerequisite release work while retaining the compensation task, first snapshot and reservations. Confirmed source-room release restores the same task's critical eligibility; a projected release cannot unlock it. This extends the existing compensation decision without changing the legacy automatic-rescue snapshot protocol.

Concept-impact review retains Scheduling Plan, Actual and Projected Occupancy and Dynamic Shift Transition names, meanings and boundaries. The change repairs execution ordering and restoration ownership under their existing contracts; no glossary edit or new invariant identifier is required.

## Verification

Offline [restoration tests](../../../../arknights_mower/tests/run_order_restoration_tests.py) exercise invalid originals, the first insertion selection failure, later selection and countdown failures, bounded restoration retries, confirmed completion, queue cleanup, original-worker reservations, cross-room shared Proviso waiting and rescue isolation. Pickle checkpoint replays cover confirmation, Grandet waiting, an empty saved plan and both `back_to_index` settings; each resumes only original-roster restoration.

The source-release regression in the restoration suite runs real `scheduling(..., op_data=...)` and `infra_main` cycles: the source facility's `SELF_CORRECTION` completes through ordinary shift projection, selection and room readback, then the same queued task restores its original roster. Screen I/O is replaced offline; the test does not manually free the original worker between dispatches. Saved restoration, insertion and empty plans, each with or without a later queued insertion, complete without selecting Proviso again or using Drone Acceleration. A transient source-facility selection error also completes through bounded retries before original-roster restoration.

The [priority-admission suite](../../../../arknights_mower/tests/priority_admission_tests.py) distinguishes Actual and Projected Occupancy, preserves waiting task objects and reservations across repeated admission passes, and verifies critical windows yield while blocked and protect restoration once ready. The [scheduler-task suite](../../../../arknights_mower/tests/scheduler_task_tests.py) verifies restoration priority, staffing-only time estimates, strict release protection and exclusion from drone order adjustment. The [base-scheduler suite](../../../../arknights_mower/tests/base_scheduler_tests.py) covers real scheduler dispatch and queue retention. These offline checks do not identify the historical cause of room displacement in the incident.
