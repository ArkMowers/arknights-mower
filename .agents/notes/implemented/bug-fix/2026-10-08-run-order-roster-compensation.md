---
title: Run Order Roster Compensation
status: implemented
category: bug-fix
date: 2026-10-08
---

# Run Order Roster Compensation

[中文](2026-10-08-run-order-roster-compensation.zh.md)

## Decision and Rationale

The [incident analysis](../../../../docs/postmortem/2026-10-01-proviso-run-order.md) records a vacant original roster restored through `Free` selection and an earlier failed restoration whose task plan is empty. The previous static main roster fallback in `BaseSchedulerSolver.agent_arrange` also mixed observed workers with configured targets; it could replace a working substitute with a resting primary. Neither source establishes the actual original workers.

One task-owned observation supplies the original roster from before insertion through verified restoration. Removing the competing static fallback is part of this compensation repair, with no independent public interface, alternate roster resolver or configuration switch.

The repair extends existing [INV-SCHED-04](../../../../CODING_STANDARDS.md#2-subsystem-invariants), whose full operational rules live in the [shift compensation contract](../../../../docs/subsystems/base-scheduler.md#251-shift-compensation-and-run-order-restoration). Invalid normal originals return to ordinary correction. Incomplete insertion, local failures and saved-task reentry retain the same original roster and resume restoration only. All queued normal insertions wait while restoration is pending, protecting shared trade order agents such as Proviso. Automatic rescue retains its distinct observed-vacancy semantics.

The queue saved by `record.current_state` shares the executing task. A checkpoint during confirmation or Grandet waiting can therefore contain the pending marker with an insertion plan or empty plan. Normalizing at queue recovery, scheduler restart and arrangement entry closes these real reentry paths. Executable restoration retains critical priority while budgeting only remaining staffing work, without Grandet waiting or drone order adjustment.

Unconditional critical protection of a restoration waiting on occupied originals can postpone the source facility's correction at every retry. A later insertion waiting on that restoration can perpetuate the same dependency. Readiness derived from Actual Occupancy permits prerequisite release work while retaining the compensation task, first snapshot and reservations. Confirmed source-room release restores the same task's critical eligibility; a projected release cannot unlock it. This extends the existing compensation decision without changing the legacy automatic-rescue snapshot protocol.

Fresh automatic rescue admission can also remove ordinary correction in the source room while compensation still waits on that room's worker. Rescue staffing then waits on the compensation's reservations, leaving neither operation able to proceed. Completing pending normal compensation before fresh rescue admission or its queue replacement for native handoff preserves the prerequisite release work. An already active rescue episode instead defers compensation rooms and retains their outstanding targets while arranging other eligible rooms, allowing source workers to be released without declaring partial staffing complete. Matching a rescue target against a temporary run-order occupant can otherwise clear that room before compensation changes its staffing again; both deployment admission and verification retain the room until compensation completes. Its specialized restoration protocol remains separate.

Maintenance backup entry calls order adjustment directly, outside normal scheduling. Advancing a waiting insertion or retaining an unavailable marked restoration in the maintenance batch can again block source staffing. Sharing the waiting-task exclusion at adjustment and maintenance entry preserves the prerequisite release; executable marked restoration retains batch protection.

The main loop also reschedules after depot scanning dispatches due mastery work. Omitting Actual Occupancy at that entry protects an unavailable restoration again and postpones its source-room correction until after the next restoration retry. Passing the existing `Operators` data preserves source release eligibility under the same admission contract.

Concept-impact review retains Scheduling Plan, Actual and Projected Occupancy and Dynamic Shift Transition names, meanings and boundaries. The change repairs execution ordering and restoration ownership under their existing contracts; no glossary edit or new invariant identifier is required.

## Verification

Offline [restoration tests](../../../../arknights_mower/tests/run_order_restoration_tests.py) exercise invalid originals, the first insertion selection failure, later selection and countdown failures, bounded restoration retries, confirmed completion, queue cleanup, original-worker reservations, cross-room shared Proviso waiting and rescue isolation. Pickle checkpoint replays cover confirmation, Grandet waiting, an empty saved plan and both `back_to_index` settings; each resumes only original-roster restoration.

The source-release regression in the restoration suite runs real `scheduling(..., op_data=...)` and `infra_main` cycles: the source facility's `SELF_CORRECTION` completes through ordinary shift projection, selection and room readback, then the same queued task restores its original roster. Screen I/O is replaced offline; the test does not manually free the original worker between dispatches. Saved restoration, insertion and empty plans, each with or without a later queued insertion, complete without selecting Proviso again or using Drone Acceleration. A transient source-facility selection error also completes through bounded retries before original-roster restoration.

The [priority-admission suite](../../../../arknights_mower/tests/priority_admission_tests.py) distinguishes Actual and Projected Occupancy, preserves waiting task objects and reservations across repeated admission passes, and verifies critical windows yield while blocked and protect restoration once ready. The [scheduler-task suite](../../../../arknights_mower/tests/scheduler_task_tests.py) verifies restoration priority, staffing-only time estimates, strict release protection and exclusion from drone order adjustment. The [base-scheduler suite](../../../../arknights_mower/tests/base_scheduler_tests.py) covers real scheduler dispatch and queue retention. These offline checks do not identify the historical cause of room displacement in the incident.

The [automatic-rescue suite](../../../../arknights_mower/tests/automatic_rescue_tests.py) covers fresh admission with saved restoration, insertion and empty plans, then resumed active staffing with original, different and currently temporary rescue targets. Source staffing releases the original worker before restoration; deferred rescue targets remain outstanding until compensation completes and their final staffing is confirmed. Cases with only a deferred room also reject completion from a temporary target match, including saved completion flags. Five new regression cases fail before the completion repair; all seven new cases pass afterward. The [maintenance suite](../../../../arknights_mower/tests/maintenance_run_order_tests.py) exercises direct adjustment and real backup entry, including previously marked tasks and source shift projection with unavailable or ready restoration.

The [scheduler-recovery suite](../../../../arknights_mower/tests/scheduler_recovery_preservation_tests.py) exercises real `simulate` and `scheduling` calls after depot scanning and due mastery dispatch. With device and scan I/O replaced offline, the regression verifies immediate source-room correction dispatch and unchanged restoration time and snapshot. The regression fails before the entry passes Actual Occupancy; all 147 tests in the suite pass after the repair.

Verification after rebasing onto `ed674a9f9a448c3839b379fdf219760c33387121` runs fourteen focused offline suites with network connections and HTTP requests blocked in the test process: 815 tests and 52 subtests pass. The [run-order planning wakeup suite](../../../../arknights_mower/tests/run_order_planning_wakeup_tests.py) verifies that completed backup staffing resumes normal planning across deferral and restart; the existing completion rule remains in the shift compensation contract. Scoped Ruff lint and formatting checks pass. `python scripts/verify_governance.py --base ed674a9f9a448c3839b379fdf219760c33387121` passes all three governance gates with two unchanged warnings for archived test references.
