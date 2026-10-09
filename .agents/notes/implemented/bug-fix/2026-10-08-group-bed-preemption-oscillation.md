---
title: Group Bed Preemption Interrupts Priority Recovery
status: implemented
category: bug-fix
date: 2026-10-08
---

# Group Bed Preemption Interrupts Priority Recovery

## Scope

This change implements [INV-SCHED-37] using the October 8 [Scheduling Plan](../../../../arknights_mower/tests/fixtures/scheduler_incident_plan_20261008.json) and [observed state](../../../../arknights_mower/tests/fixtures/scheduler_incident_20261008.json). The captured incident reproduces on baseline `87b9d3aa` and the isolated repair base `31709700`. Related contracts are [INV-SCHED-05], [INV-SCHED-20] and [INV-SCHED-21] in [Coding Standards](../../../../CODING_STANDARDS.md).

## Evidence

| Time | Observation |
| --- | --- |
| 11:05:55.813 | Complete Shift Convergence places 歌蕾蒂娅 in dormitory 1, slot 4, with the 深海 group resting. |
| 11:07:47.603 | The room reading records her mood as 0; the saved bed completion time is 18:44:53.645. |
| 11:09:22.723 | `restore_displaced_resting` reports that bed preemption recalls the entire 深海 group. |
| 11:09:23.534 | Complete Shift Convergence assigns 歌蕾蒂娅 to the Control Center. |
| 11:12:35.126 | The next measured working mood remains 0. |
| 11:12:39.505 | Complete Shift Convergence places her back in dormitory 1, slot 4. |

The configuration gives 歌蕾蒂娅 concentrated recovery priority and marks 乌尔比安、斯卡蒂、安哲拉、幽灵鲨 as low-priority resting members. The 红松 group preempts beds occupied by those lower-priority members. The `11:09` pre-dispatch queue contains one newly generated SHIFT_OFF; the return appears in its concrete plan before complete convergence.

## Cause

[`_get_resting_plan`](../../../../arknights_mower/solvers/base_schedule.py) allocates beds for a waiting group, then calls [`restore_displaced_resting`](../../../../arknights_mower/utils/scheduler_task.py). Displacement of one incomplete mandatory primary adds every member of its group to the working arrangement and resets the recalled members' beds. The recall does not evaluate each other member's mood or concentrated recovery priority.

An individual bed takeover therefore interrupts an entire recovery group, including a priority member whose recovery completion is over seven hours away. Her subsequent zero-mood working observation creates another exhausted shift. Backup conditions tied to 薇薇安娜 and 歌蕾蒂娅's resting state follow these changes and switch the working rosters again.

Complete Shift Convergence settles the current task's projection. Its local `returning` set excludes just-returned members from another off-shift attempt within that pass. That protection ends with the pass; it does not establish recovery stability across subsequent observations and tasks.

## Admission Contract

[INV-SCHED-37] requires the requester to outrank every unfinished non-dormitory, non-workaholic member affected by group recall. This includes members without a bed and members with unknown mood. A completed member does not protect unfinished lower-tier peers. Completed or standby departures retain unfinished group recovery and return tasks when a required recovery anchor remains.

Recovery completion requires a valid mood reading and excludes an expired-timer prediction. A passed bed deadline alone cannot permit takeover after an unfinished or unknown observation. Current and omitted positions retain their resident only when the final arrangement does not explicitly move that name elsewhere. Fixed group recovery beds contribute retained anchors without becoming ordinary dynamic beds.

Complete group admission filters each bed candidate against the pending arrangement, then rechecks the final arrangement before writing any bed reservations. A takeover whose final arrangement removes the required recovery anchors uses the full group recall rule. An ineligible candidate does not suppress another legal lower-tier bed. A rejected arrangement leaves existing beds, recovery deadlines and the caller's plan intact. Strictly higher recovery applicants retain legal group preemption. The displaced group cannot reclaim these beds through an equal or lower-tier request immediately afterward. Personal limits, reservations, exclusions and explicit task execution retain their existing boundaries.

## Implementation and Simplification Check

`Operators.resting_recall_members` supplies the same recall membership to admission and displaced-bed compensation. `resting_recovery_complete` shares completion evidence across recall, allocation, idle bed filling and dispatch-time Free selection. `_resting_residents` resolves final slot identities, including explicit moves and new reservations; `_retained_resting_members` derives the retained names used by `_resting_preemption_allowed`. `restore_displaced_resting` uses that same slot resolution and pads short work or dormitory destination rows with Current to their configured length before writing compensation targets. Candidate filtering and final `assign_dorm_group` validation precede reservation writes. Idle filling and Free selection reject an ineligible bed before consuming its recovery applicant, so another legal bed remains available.

Automatic named dispatch reapplies shared critical-task admission after regeneration changes the plan or type, before fallback-state writes or live compensation. [INV-SCHED-36] can defer or reshape that arrangement while [INV-SCHED-37] keeps observed recovery protected; the [execution decision](2026-10-08-named-bed-preemption-revalidation.md#shared-planner-implementation) owns this production boundary.

[`emergency_dorm_plan`](../../../../arknights_mower/utils/emergency_recovery.py) keeps the complete bed pool on its probe. Reserved, protected and already assigned positions are excluded by index, while their residents remain visible to group recall checks. Resident identity falls back to the actual operator when a bed cache lacks its name. Emergency reallocation clears only eligible copied beds and preserves the observed state. These changes use existing projection and allocation boundaries without persistent scheduling state or a new task type.

## Verification and Limits

The [offline incident regression](../../../../arknights_mower/tests/scheduler_incident_20261008_tests.py) restores captured operators, effective backup conditions and nine bed records. It executes real `resting`, `_plan_primary_recovery`, idle filling and group recall. Three rounds with repeated zero-mood `update_detail` observations and both primary-then-fill and fill-then-primary task orders project the newly due arrangements and keep 歌蕾蒂娅 resting. The original bed-protection control remains a comparison case.

The [focused admission tests](../../../../arknights_mower/tests/group_preemption_stability_tests.py) cover equal-tier and lower-tier interruption rejection, unknown or predicted mood, members without beds, legitimate higher-tier recall, completed priority members, atomic allocation failure and legal alternative beds. Dispatch tests run `agent_arrange` through Free resolution and compensation, stopping at the device boundary. They cover expired deadlines after actual `update_detail` observations, explicit anchor departures with Current, omitted or short dorm rows, final worker positions and obsolete return-task removal. Protected emergency anchors are tested with and without cached bed names. Eleven boundary cases fail on the reviewed implementation before this repair.

[Fixed group recovery coverage](../../../../arknights_mower/tests/same_group_dorm_replacement_tests.py) executes allocation and dorm arrangement merging before checking the final projection. Neighboring standby, completed departure, emergency reservation, single-target admission, Fiammetta, isolation and shift convergence cases pass. Governance gates check document structure, links and terminology; functional assertions establish scheduling behavior. The standards and requirement findings also include manual examination of production callers and mutation order.

```text
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'preemption or priority_recall' -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/group_preemption_stability_tests.py arknights_mower/tests/resting_preemption_tests.py arknights_mower/tests/completed_group_departure_tests.py arknights_mower/tests/emergency_group_beds_tests.py arknights_mower/tests/shift_cycle_convergence_tests.py arknights_mower/tests/fiammetta_dorm_isolation_tests.py arknights_mower/tests/dorm_admission_priority_tests.py -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/same_group_dorm_replacement_tests.py -k 'complete_shift_uses or fixed_alternative or normal_rotation_uses or fixed_target_is_preserved or reserved_fixed_slot or yields_with_required_anchor' -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/automatic_rescue_tests.py -k 'entry_reallocat or entry_dorm_plan' -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/dorm_isolation_tests.py -k 'emergency_' -q
python -B -X utf8 scripts/verify_governance.py
```

The snapshot reconstructs planning from logged observations and the captured configuration. It omits device input and does not replay the entire game session. Runtime source line positions differ from this committed baseline; the offending planning behavior reproduces on the baseline. Initial validation uses review commit `42bf3467` plus the admission and Free repair, with comparison base `31709700`. Those tests update observations before admission or dispatch Free placeholders; the repeated-task incident test projects generated plans directly. They do not establish execution safety for automatically generated named takeovers after a changed observation or occupant. The [automatic named takeover decision](2026-10-08-named-bed-preemption-revalidation.md) defines dispatch revalidation and its additional offline evidence. That pre-rebase validation excludes the full test suite, unrelated incident cases and compatibility with newer alpha commits. Its governance script has three structural gates and no comparison-base option; the rebase target's current governance entry accepts `--base` for changed-reference validation.

The [deferred-task duplication record](2026-10-08-deferred-exhaust-task-duplication.md) documents the separate queue accumulation that precedes this sequence.

## Standards Findings

The initial review covers shared recall membership and final slot identity, finite bed and group traversal, isolated projections, reservation ownership, exact domain terms and focused offline tests. Its governance and Ruff results concern document structure and Python style. These checks do not establish dispatch compliance with [INV-SCHED-37] after an automatic named takeover's admission evidence changes. Existing domain definitions are unchanged.

## Spec Findings

The initial passing cases cover ordinary allocation, idle filling with unchanged admission evidence, Free dispatch, final group admission rejection, completed or standby departures with final retained anchors, explicit work departures, higher-tier admission and protected-anchor emergency filling. The incident test's repeated observations and both task orders preserve priority recovery through direct projection of newly generated arrangements. Automatic named takeover dispatch after changed observations or occupant identity remains outside those passing cases and is covered by the linked execution decision.

## Rebase Integration

The first alpha rebase target is `9028fd00b123e610d1db50aa8f88e53c96878543`. The complete pre-rebase repair is preserved at `85f69f66ea63bbda44419956933fde29f3c090bb`, including the saved working-tree repair beyond initial HEAD `42bf34678418af88a2bf2dfc879b538320aa4fe2`. That independent review covers this target SHA through the then-final working tree, including uncommitted changes, and checks preservation against the complete repair from `3170970051c8b4204c65260aa449aaf81fe130f0`.

The first merge preserves this admission decision and the separate [automatic named execution decision](2026-10-08-named-bed-preemption-revalidation.md), with their bilingual mirrors and metadata. During that integration, the upstream recycling guarantee moves from the colliding [INV-SCHED-37] identifier to [INV-SCHED-40]; its full guarantee and references remain intact. Existing pending-exhaust, idle-observation, scheduling-cursor and right-side staffing contracts remain active. The implemented deferred-exhaust and idle-observation records own their existing decisions; replayed diagnostic proposals add no independent contract and their valid evidence remains in those owners and the saved Git history.

Group priority, recovery anchors, automatic execution revalidation and compensation isolation change operational rules within existing Dormitory Bed Priority, Complete Shift Convergence and Actual and Projected Occupancy concepts. Their names, meanings, boundaries and relationships remain unchanged, so [INV-06] requires no glossary edit. Historical test and review declarations above describe pre-rebase evidence.

### First Alpha Offline Checks

The first rebased HEAD is `ef99a0daab457048e76706e8a87f18cadffb23c8`. The checks below record verification against the first target `9028fd00b123e610d1db50aa8f88e53c96878543`, with the subsequent short-row repair, fixture alignment, critical-window repair, regressions, documentation and formatting changes in that working tree. Their results are historical evidence for the first integration.

The first focused run produces four failures: three parameterized cases assume the old bed order, and one exposes an IndexError when compensation writes a short dormitory row. The fixture now identifies the actual group member at dormitory 2, slot 2 and verifies that it belongs to `DEEP[1:]`; the automatic named occupant still differs from the original recovery applicant after single-target reordering. The explicit-departure fixture selects a yielding bed in a different dormitory from the anchor, so assigning the anchor's short row preserves the valid takeover arrangement. Bed, deadline, return-task and rejection assertions remain intact. Current padding fixes the production short-row failure through the existing regression case.

```text
python -X utf8 -m pytest -q arknights_mower/tests/group_preemption_stability_tests.py arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'preemption or priority_recall'
```

Independent requirement review then reproduces a P2 interaction with [INV-SCHED-36]: automatic rebuilding increases the arrangement estimate from 100 to 460 seconds, but the old admission still permits dispatch into the next critical window. Rechecking the shared priority guard before live writes fixes that path. The two new RUN_ORDER and enabled SWAP_SUPPORT cases fail before repair and pass afterward; the [execution record](2026-10-08-named-bed-preemption-revalidation.md#first-alpha-execution-repair-evidence) preserves the independent replay's timing and state evidence.

The final repaired run passes 52 cases: all 48 stability cases and four selected incident cases; four other incident cases are deselected. Final neighboring offline verification passes 406 cases across `resting_preemption_tests.py`, `completed_group_departure_tests.py`, `same_group_dorm_replacement_tests.py`, `fixed_dorm_cover_admission_tests.py`, `dorm_priority_refresh_tests.py`, `emergency_group_beds_tests.py`, `dorm_admission_priority_tests.py`, `fiammetta_dorm_isolation_tests.py`, `shift_cycle_convergence_tests.py`, `dorm_isolation_tests.py`, `dorm_run_order_guard_tests.py`, `priority_admission_tests.py` and `mastery_scheduling_tests.py`, all under `arknights_mower/tests/`. That run reports the same two Pydantic serializer warnings.

```text
python -X utf8 scripts/verify_governance.py --base 9028fd00b123e610d1db50aa8f88e53c96878543
python -X utf8 -m pytest -q arknights_mower/tests/verify_governance_tests.py
```

All three governance gates pass. Two unchanged archived ADB records produce test-reference compatibility warnings. The focused governance suite passes 25 tests and 21 subtests. Ruff lint and formatting checks pass for the four production and three test files. Governance results establish structural validity; behavior, semantic review and glossary approval remain separate checks.

These first-integration runs use offline test doubles and stop dispatch before device input. They do not start the game, connect to devices or run the complete suite. The corresponding independent standards and requirement reviews cover the first target SHA through that final working tree, including uncommitted changes. Their review report records conclusions separately from these behavior and structural check results.

## Latest Alpha Integration for the PR

The latest actual alpha target is `4edfb1a57f715d284376d1473056649253ec0ed1`, nineteen commits beyond the first target. The complete first-integration repair and working-tree changes are preserved at `76e3df9aded0481e709fb3a89b6637806a8f83aa` on `backup/group-bed-preemption-complete-pr-20261009` before the branch is consolidated and rebased again. The current independent review scope is this new target SHA through the final working tree, including uncommitted changes. Preservation is compared with the original repair base `3170970051c8b4204c65260aa449aaf81fe130f0` and the complete saved repairs.

The new target owns [INV-SCHED-40] Confirmed Crafting Dispatch. Recycling retains its unchanged guarantee under [INV-SCHED-41], and Group Preemption Priority remains [INV-SCHED-37]. This integration retains complete-group priority, final recovery anchors, legal alternative beds, automatic named dispatch revalidation, planning-time compensation isolation, the actual-occupant snapshot, short-row compensation and renewed critical-task admission, with existing specialized-task boundaries.

The first target's 52 focused and 406 neighboring cases above remain historical results. Latest-target focused verification after the test-isolation repair passes 52 cases, with four incident cases deselected. Guards intercept `requests.Session.request`, socket connection and `sqlite3.connect`; the run reports zero attempts. The existing domain-concept assessment remains unchanged, and neither glossary is edited.

Neighboring verification against the latest target passes 512 cases across the first integration's thirteen suites plus `mastery_maintenance_tests.py`, `maintenance_run_order_tests.py` and `workshop_mastery_dispatch_tests.py`, all under `arknights_mower/tests/`. The two Pydantic serializer warnings arise from legacy Task/Trigger dictionaries in `dorm_priority_refresh_tests.py`. The subsequent guarded neighbor audit initially catches an announcement request in the enabled SWAP_SUPPORT initial-Fiammetta case; that existing test now uses `offline_maintenance` without changing its assertions. After the correction, the guarded rerun passes the same 512 cases with the same two warnings and zero request, socket or workspace-SQLite attempts. It uses an independent `MOWER_DATA_DIR` and permits only temporary test databases. All eight changed Python files pass Ruff lint and formatting checks; `git diff --check` passes.

The current structural command is `python -X utf8 scripts/verify_governance.py --base 4edfb1a57f715d284376d1473056649253ec0ed1`. Its actual result and the independent review conclusions belong in the final review report, separately from these behavior results. Current review uses the new fixed target through the final working tree, including all uncommitted changes; earlier target results do not certify this range.

## CI Regression Alignment

CI at `56c27c477aba19e5bbafe7d52daf1a27b9a03605` reports eight failures. The focused local reproduction matches all eight: six legacy cases treat an expired bed countdown as recovery completion despite unfinished or unknown mood, and two reduced `SimpleNamespace` fixtures omit interfaces reached by the shared recall policy. The run-order failure fixture now uses `Operators`; the reserved product-bed fixture uses `Operator`. Both retain their original task-preservation and reservation assertions.

The [release suite](../../../../arknights_mower/tests/dorm_release_tests.py) records measured completion with `update_detail` and covers personal upper limits of 12, 20 and 24. Unfinished residents retain their beds with missing, future or expired deadlines. The [unknown-selection suite](../../../../arknights_mower/tests/dorm_unknown_selection_tests.py) checks unknown, invalid and predicted readings independently of the deadline, preserves the original mood and bed state, and verifies that measured completion permits the same takeover during planning and selection. The focused CI reproduction and completion controls pass 41 cases.

The [automatic dispatch suite](../../../../arknights_mower/tests/group_preemption_stability_tests.py) adds three configuration-change cases after legal admission: a requester loses priority, an existing member gains priority, or a newly bound group member has equal priority. Dispatch rejects the obsolete recall before device input and preserves beds, deadlines and queued group returns. All three pass. These tests extend [INV-SCHED-37] evidence within the existing scheduling concepts; [INV-06] requires no glossary edit.

Final offline verification at the same HEAD plus these test repairs passes 956 cases across 22 focused scheduling suites, with three warnings. Socket connections and workspace SQLite access are guarded; both attempt counts are zero. `MOWER_DATA_DIR` points to an independent temporary directory. Review against `4edfb1a57f715d284376d1473056649253ec0ed1` covers the complete PR and these repairs, including allocation, ordinary and automatic dispatch, compensation, emergency admission, reservations and critical-task protection. No remaining confirmed standards or requirement defect is found in that scope. Offline dispatch stops before device input; live-device behavior remains outside this verification.
