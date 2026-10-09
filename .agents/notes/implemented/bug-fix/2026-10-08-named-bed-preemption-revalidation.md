---
title: Automatic Named Bed Takeovers Revalidate Group Priority
status: implemented
category: bug-fix
date: 2026-10-08
---

# Automatic Named Bed Takeovers Revalidate Group Priority

## Contract

[INV-SCHED-37] applies both at bed admission and before execution of an automatically generated named bed takeover. Current observations, actual occupant identity, recovery tiers and the complete final arrangement determine whether the applicant can displace a resident and recall its group. Admission evidence does not authorize a later recall when that evidence changes.

An automatic takeover that recalls a recovery group requires the applicant to outrank every unfinished non-dormitory, non-workaholic member affected by the recall, including members without beds. Completed or standby departures remain valid with a retained required recovery anchor. Explicitly departing names do not count as retained anchors, including departures whose old dormitory rows use Current, are omitted or are short.

Automatic task creation generates displaced-bed compensation on an isolated projection and a copy of pending tasks. It preserves live beds, recovery deadlines and group return tasks even when admission currently permits a complete group recall. Execution revalidation precedes live compensation, bed resets, group return-task cancellation and device input. Rejection retains the protected occupant, bed identity, recovery deadline and ordinary group return tasks. It does not add the group to working arrangements. The rejected applicant remains eligible for another legal bed in the same automatic arrangement. Reservations, exclusions, personal limits and strictly higher-priority admission remain binding.

## Scope and Production Boundary

[`try_add_release_dorm`](../../../../arknights_mower/utils/scheduler_task.py) creates automatic named takeovers and records their admission arrangement in `task.dorm_fill_plan`. `agent_arrange` in the [scheduler solver](../../../../arknights_mower/solvers/base_schedule.py) rebuilds unstarted standalone `NOT_SPECIFIC` and `FILL_DORM` tasks carrying that existing arrangement before `restore_displaced_resting` commits compensation. A named target alone does not identify an automatic admission; explicitly requested tasks without that arrangement retain their behavior.

Rebuilding excludes emergency dormitory tasks, frozen emergency scheduling and tasks carrying `arrangement_retry_room`, `dorm_recovery_restore`, `product_shift_locked`, `backup_shift_active` or `strict_mood_limit`. These boundaries retain started room retries, single-target restoration, product and backup transitions, mandatory releases and emergency admission policy. Complete ordinary shifts retain their existing Complete Shift Convergence path; Fiammetta charging and restoration retain their task boundary.

## Shared Planner Implementation

`agent_arrange` creates `Operators.project_arrangements([{}])` to reconcile copied recovery beds with actual occupant positions, and deep-copies the other pending tasks. It invokes the existing `try_add_release_dorm` against that isolated state. The shared planner applies current completion evidence, occupant identity, recovery tiers, reservations and the complete arrangement through the existing admission and recall policy.

The copied tasks' object identities distinguish a newly generated task from retained tasks, with strong references preventing identity reuse. `try_add_release_dorm` generates the compensation plan on another projection and a copy of pending tasks; its planning-time bed resets and return-task cleanup do not affect either the live state or the dispatch observation. Planning leaves the live queue unchanged; execution subsequently applies shared critical-task admission before final compensation against the selected arrangement.

Regeneration retains the current task's object identity and original execution time, applies the generated plan and type, then replaces or clears `dorm_fill_plan`, `dorm_mood_residents` and `simple_dorm_fill` according to the generated task. Before fallback-state writes, live compensation or device input, `protect_priority_tasks` reevaluates the regenerated plan and type under [INV-SCHED-36]. Shared critical-task admission can defer the task or change its plan. A future task, empty queue or different queue head returns False so the scheduler selects the next eligible task; continued dispatch uses `self.task.plan` rather than the original arrangement reference. A selected occupant with an existing projected `dorm_mood_fallback` receives its final dormitory room, including after single-target reordering. Low-mood applicants acquire no full-mood fallback protection. If the planner generates no task, the current task's plan is cleared and obsolete fill metadata is removed.

Execution saves the actual occupant mapping before regeneration and passes the same observation to `restore_displaced_resting`. The observation resolves final retained identities, recall members and the original occupants whose live bed caches are reset. Before writing compensation targets, short work or dormitory destination rows are padded with Current to their configured length, preserving unspecified positions and making target indices valid. Live beds and pending tasks receive compensation writes. A stale cached group member therefore cannot replace the actual occupant in compensation after admission has validated that actual occupant. Other callers omit the observation and retain their existing bed-reservation semantics. Existing Free resolution consumes the current arrangement before compensation.

The [initial group-preemption decision](2026-10-08-group-bed-preemption-oscillation.md) defines ordinary admission and Free dispatch. Its initial passing cases do not cover an automatic named takeover between changed admission evidence and execution. [Coding Standards](../../../../CODING_STANDARDS.md) and the [Base Scheduling Contract](../../../../docs/subsystems/base-scheduler.md) register the same invariant; this record adds execution coverage to that invariant.

## Pre-flight Simplification

The production caller scan finds existing shared policy boundaries: `Operators._resting_preemption_allowed` serves allocation, idle filling and Free dispatch; `_retained_resting_members` resolves the complete final arrangement; `resting_recall_members` shares recall membership with compensation. `task.dorm_fill_plan` already records automatic admission targets and participates in planning, reservations and selection. Reusing `try_add_release_dorm` applies all those boundaries together, including legal alternatives and single-target ordering, without identifying an applicant from the reordered occupant. The implementation adds no helper, task type, configuration field or persistent scheduling state. No separate abstraction removal is proposed.

## Added Regression Cases

The [focused stability suite](../../../../arknights_mower/tests/group_preemption_stability_tests.py) adds actual automatic task creation followed by `agent_arrange`, stopping at the device boundary. Three observation cases admit an idle priority replacement to a completed low-priority group member's bed while an unfinished priority anchor remains, then use `update_detail` before dispatch to record unfinished recovery, unknown mood or a predicted completion. Each case repeats creation and dispatch twice and asserts preserved beds, recovery deadlines, ordinary return-task identity and projected group recovery.

The suite adds 18 parameterized cases covering the changed automatic execution boundary:

- Completed and standby departures retain required recovery anchors; strictly higher-tier arrivals still recall the lower-tier group and cancel obsolete return tasks.
- An initially legal complete group recall preserves all live beds and return tasks at admission; an unfinished observation before dispatch rejects it without losing that state.
- Actual occupants override stale cached identities consistently at admission and compensation, both when takeover is refused and when another resident legitimately returns to work.
- A rejected applicant uses another legal bed in the same or a later automatic task; pending bed and applicant reservations remain binding.
- Regeneration changes between `NOT_SPECIFIC` and `FILL_DORM`, keeps task identity and its original time before shared critical-task admission, and updates simple-fill metadata.
- Known full-mood fillers retain fallback protection in the final room; started room retries and single-target restoration keep their confirmed arrangements.

## Verification and Limits

The following counts and review declarations record verification of the complete pre-rebase repair at `85f69f66ea63bbda44419956933fde29f3c090bb`. The [first alpha rebase record](2026-10-08-group-bed-preemption-oscillation.md#rebase-integration) and [first alpha offline checks](2026-10-08-group-bed-preemption-oscillation.md#first-alpha-offline-checks) record the earlier integration's scope and results. The current target and comparison scope belong to the [latest alpha integration](2026-10-08-group-bed-preemption-oscillation.md#latest-alpha-integration-for-the-pr).

Focused offline verification passes 46 stability cases and four incident cases selected by `preemption or priority_recall` (four other incident cases deselected). Neighboring verification passes 195 cases covering resting preemption, same-group dormitory replacements, completed departures, admission priority, emergency group beds, Fiammetta isolation and dormitory isolation, plus 191 cases covering run-order guards, idle searches, mood fallback, exclusions, estimated recovery, unregistered occupants, workshop dispatch and complete-shift convergence.

`python scripts/verify_governance.py` passes all three gates for triplets, links and controlled language. The focused governance suite passes 14 tests and four subtests. Ruff lint and formatting checks pass for the three Python files changed by this execution repair. Independent requirements and repository-standards reviews find no remaining confirmed defect in the reviewed production callers and mutation order against [INV-SCHED-37]; their final conclusions use static evidence, with runtime verification provided by the offline tests above.

The pre-rebase verification above has no separate regression for changes to group bindings or recovery-tier configuration after admission. Current configuration-change coverage is recorded in [CI regression alignment](2026-10-08-group-bed-preemption-oscillation.md#ci-regression-alignment). Existing final-anchor cases cover pending arrangements at admission or explicit dispatch. The incident suite's two ordinary planning orders project generated arrangements and do not execute each automatic named task. Offline dispatch tests stop before device input and do not replay a complete game session. The full test suite and live-device integration remain outside this local verification.

## First Alpha Execution Repair Evidence

On rebased HEAD `ef99a0daab457048e76706e8a87f18cadffb23c8`, the existing short-row explicit-anchor-departure case exposes a compensation IndexError. Padding work and dormitory destination rows with Current before target writes repairs that production path. Fixture alignment follows the upstream bed order while preserving the actual group resident, the distinction between the original applicant and the reordered named occupant, and all protected-bed, deadline, return-task and rejection assertions. The anchor's short row occupies a different dormitory from the yielding bed, preserving the intended admission while exercising compensation.

Independent requirement review also reproduces a critical-window violation: changed actual residents expand an automatic one-dormitory `FILL_DORM` plan estimated at 100 seconds into a `NOT_SPECIFIC` plan with four work rooms and three dormitories, estimated at 460 seconds. Earlier protection sees only the original plan. Reapplying shared priority admission after regeneration repairs that interaction with [INV-SCHED-36]. `test_automatic_group_preemption_rechecks_expanded_task_before_critical_dispatch` covers RUN_ORDER and enabled SWAP_SUPPORT; both cases fail before the repair and pass afterward. The independent replay returns False, defers the 12:00 ordinary task to 12:02:51, retains the critical task at 12:02:50 and makes no room call. Beds, recovery deadlines and the SHIFT_ON task's object, time and plan remain unchanged.

The first alpha integration's final focused checks pass 48 stability and four selected incident cases, with four incident cases deselected, plus 406 neighboring offline cases. The linked first-alpha check record owns the exact commands, suite scope, governance results and warnings. These results include that integration's working tree; dispatch remains stopped before device input. Its independent standards and requirement conclusions use `9028fd00b123e610d1db50aa8f88e53c96878543` through the then-final working tree, including uncommitted changes. They are historical evidence for that target.

## Latest Alpha Dispatch Verification Scope

The current actual target is `4edfb1a57f715d284376d1473056649253ec0ed1`; the complete repair before this second rebase is preserved at `76e3df9aded0481e709fb3a89b6637806a8f83aa`. Current independent review covers that target SHA through the final working tree, including uncommitted changes. The shared planner, group-priority revalidation, actual-occupant observation, isolated compensation, short-row handling and renewed critical-task admission retain the same contracts and specialized-task exclusions.

Independent standards review identifies focused-test isolation gaps after the newer alpha integration. The stability suite's autouse fixture now depends on `offline_maintenance` and replaces `mastery_db.get_active_plan` with an empty result. The incident clock fixture also depends on `offline_maintenance` and replaces `record.save_agent_action` with a no-op. The existing initial-Fiammetta critical-task case also uses `offline_maintenance` to isolate its announcement check. These boundaries isolate announcement checks, mastery database reads and mood-history writes while retaining the original scheduling assertions. The subsequent CI review adds three formal configuration-change cases in `group_preemption_stability_tests.py`; [CI regression alignment](2026-10-08-group-bed-preemption-oscillation.md#ci-regression-alignment) records their coverage and results.

The [latest integration record](2026-10-08-group-bed-preemption-oscillation.md#latest-alpha-integration-for-the-pr) owns this rebase target, numbering reconciliation and current check results. The latest guarded focused run passes 52 cases with four deselected and zero requests, socket or SQLite attempts. The corrected guarded neighbor run passes 512 cases with two legacy Pydantic warnings and zero network or workspace-database attempts, using independent runtime storage and permitting temporary test databases. All eight changed Python files pass Ruff checks. The 52 focused and 406 neighboring passes recorded above apply to the first alpha target. Latest-target behavior, isolation, structural and independent review results remain separate evidence.
