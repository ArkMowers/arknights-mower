---
title: Protected Dormitory Bed Tiers
status: implemented
category: bug-fix
date: 2026-10-09
---

# Protected Dormitory Bed Tiers

## Contract

[INV-SCHED-43] protects occupied recovery beds of explicit-priority operators, normal primaries, low-priority primaries and priority replacements. These four tiers displace standby primaries, ordinary replacements and idle operators. Standby primaries displace ordinary replacements and idle operators, and ordinary replacements displace idle operators, only with valid current mood no greater than 80% of their own mood upper limit. Same-tier takeovers remain denied. Completion predictions, expired deadlines and rescue mode do not bypass occupancy protection. Vacant-bed ranking and single-target position allocation retain their existing order. Ordinary returns, ordinary full-mood releases, mandatory personal-limit departures and explicit staffing tasks retain their own admission.

## Simplification Preflight

`Operators._slot_takable`, `try_add_release_dorm` and `preserve_resting_crafters` share the recovery tier enum but bypass one another for completed residents. One shared predicate expresses occupancy protection and the applicant mood threshold across all three callers; no new configuration, task type or persisted state is introduced. Automatic named fill tasks use the existing planner for dispatch validation.

## Cause and Scope

Commit `0cb1e21f7a58050999a8cb874827042defb967a1` removes the primary-resident protection barrier and permits any strictly higher tier to take over a bed. This correction restores the barrier and includes priority replacements in the protected tiers. [The previous priority decision](../../implemented/simplification/2026-10-02-priority-aware-dorm-recovery.md) retains its other recovery and reservation contracts; this record supersedes its unrestricted tier takeover rule.

## Verification

[Focused regressions](../../../../arknights_mower/tests/protected_dorm_bed_tiers_tests.py) cover occupied-bed protection, completed and unknown readings, expired deadlines, planning and Free selection, automatic named dispatch, and legal lower-tier takeovers at 80% of personal mood limits of 12, 20 and 24. A standby applicant above the threshold does not block a later eligible replacement; queued named fills recheck the applicant mood before dispatch. Tier matrices cover ordinary and rescue admission. Device inputs, live network and workspace databases are excluded.

## Dispatch and Compensation

Only unstarted automatic `NOT_SPECIFIC` and `FILL_DORM` tasks carrying `dorm_fill_plan` are rebuilt. Room retries, recovery restoration, locked product and active backup shifts, mandatory releases and emergency staffing retain their existing lifecycle. Rebuilding preserves task identity and reevaluates critical-task admission before fallback writes, live compensation and device input.

A standby departure retains any protected working group member still resting, including a completed member; the ordinary group return task governs its later return. Completed fixed managers in temporarily opened emergency slots use the existing manager-departure projection before bed admission. Explicitly prioritized managers remain protected. Free selection distinguishes the fixed dormitory primary departing its configured post from a recovery resident using that dynamic position; a temporary protected primary in the same position retains its bed. Neither operation introduces a generic recovery takeover exception.

## Review and Results

Standards axis: no remaining confirmed findings; the shared predicate has three production callers, projections isolate mutable beds and tasks, and the glossary additions use the wording explicitly approved by the user.

Requirements axis: the full tier matrices, 232 focused protection and mood-threshold cases, legal standby departures, normal and merged full-mood releases, mandatory personal limits, queued named fills and RUN_ORDER/SWAP_SUPPORT admission satisfy [INV-SCHED-43]. On alpha baseline `d4e22126`, the two focused batches pass 1156 and 309 tests, including standby capacity validation; the separate run-order planning wakeup suite passes 10 tests with temporary SQLite persistence. Network and SQLite guards on the two batches report zero attempted accesses; unrelated history, inventory and mastery observers use offline substitutes. Device selection uses offline doubles. Real game execution is outside this verification.

The structural governance gate, 25 governance tests and 21 subtests pass. Ruff checks and formatting pass for all 16 changed Python files. Two archived-note reference warnings predate this change.

The focused CI regressions and protection suite pass 634 cases, covering whole-group standby admission at and above the 80% threshold, explicit Free dormitory-primary departures, same-tier idle retention, unknown-candidate admission only after a valid reading or ordinary release, workshop replacement thresholds and product reservations. The fixture-only tier substitute covers both shared predicate callers. One existing Pydantic fixture serialization warning remains.


## Grouped Free Capacity

The same protected-bed decision also scopes the capacity released by a grouped dormitory primary with an explicit `Free` replacement. This is a count constraint across all recovery positions, not a bed-number restriction. Protected working primaries can use their own group's dynamic capacity or ordinary Free capacity; the last three tiers can use either. Group capacity is preferred, leaving ordinary capacity available to unrelated protected applicants. Matching all protected residents and pending arrivals prevents one group from borrowing another group's capacity and avoids dependence on bed order. Multiple bindings share one capacity unit and participate in matching. No persistent quota state, configuration or parallel allocator is introduced.

Allocation, automatic fill, rescue planning, named selection and unknown-card fallback call `Operators.dorm_capacity_allows`. Occupied-bed admission still checks the shared takeover predicate, so neither capacity eligibility nor recovery completion evicts a protected resident. Returning managers reclaim capacity through the existing return rebalance; protected residents may move across physical beds while a lower-tier resident leaves.

[Grouped dormitory regressions](../../../../arknights_mower/tests/dorm_group_tests.py) cover vacancy permutations, all four protected applicant tiers, all three remaining tiers, unrelated-group rejection, occupied takeovers, transactional group allocation, secondary bindings, unknown-page selection and return-time cross-position capacity reclamation. The owning invariant remains [INV-SCHED-43] and the active triplet remains implemented; this extension creates no new decision record.

The capacity, compensation and group-state extensions pass 2857 distinct focused offline cases across 52 test files, covering allocation, selection, bindings, static validation and neighboring recovery rules, with zero attempted network or SQLite accesses. Standards and requirements review confirms quantity admission, group-first matching, transactional pending arrivals, occupied-bed protection and independent group state. Ruff and structural governance checks pass; two archived-reference warnings and existing Pydantic fixture warnings remain. The bilingual glossary addition uses the exact wording approved by the user.

Static validation reuses [INV-SCHED-42]: mandatory working members count against ordinary Free capacity plus only their own group’s configured dynamic capacity. Live group state, cached occupants and another resting group’s Free capacity cannot change the result. Primary and secondary Free bindings validate when sufficient; backup combinations that remove required capacity fail. The focused validation tests also execute the accepted eight-worker off-shift arrangement to verify runtime agreement. Capacity admission reuses the existing `match_replacements` maximum matching with dynamic capacity as the preferred set, rather than introducing another matching implementation.


## Observed Occupancy and Fixed Recovery Beds

Compensation snapshots include ordinary dynamic beds and configured fixed recovery beds. Observed occupants take precedence over stale bed names. The same snapshot feeds displacement detection; group allocation supplies only its explicit new reservations through `admitted`, and the final arrangement overlays those reservations. Compensation does not reread an inconsistent cache as another group's departure. Standby and shared-primary displacement cannot recall a group, whether or not another member retains a recovery bed.

Eight new focused cases cover fixed-bed standby compensation during planning and dispatch, secondary binding membership, stale-cache named dispatch, and established single-target positions during no-op, vacancy fill and lower-tier takeover. The stale-cache case fails against the previous compensation functions and passes with the correction. The single-target cases preserve both manager and target positions, retain their confirmation record and perform no extra temporary confirmation. Existing rules still permit a legal higher-tier single-target replacement. Normal whole-group returns still include working members on fixed recovery beds; the existing fixed-return regressions remain binding. The focused compensation, recovery-position and binding batch passes 749 cases with zero attempted network or SQLite accesses.

## Independent Group State and Standby Admission

The repair also reuses [INV-SCHED-25] and the [explicit group-state decision](../simplification/2026-10-07-explicit-group-shifts.md). `Operators.is_group_shift_anchor` supplies one ordinary fixed-working-primary boundary for group mood, legacy inference, confirmed transitions, shift triggers, return timing, bed displacement, capacity rebalancing and position correction. Standby and shared-primary events do not generate group returns or remove another member’s scheduled return. This applies at zero, partial, full and unknown mood, including a standby primary temporarily ranked `LOW_MAIN`.

Standby promotion is checked before off-shift bed allocation, rather than during ordinary mood readback or scanning all workers. A promoted standby requires a bed, keeps the tier during recovery and loses it after an observed return to its working post. The optional allocator no longer silently skips a promoted standby. Static validation continues to accept sufficient mandatory capacity; runtime admission defers when current rescue promotions require additional beds. The eight-worker validation test covers both ordinary optional standby admission and mandatory promoted-standby deferral.

The new independence suite contains 58 focused cases. Its initial 38 cases reproduced 31 failures before repair; the remaining cases cover capacity closure, backup migration, dormitory correction, native recovery projection, normal-primary transitions, shared-binding return-window stability and individual standby returns. Adjacent correction, backup and confirmation suites verify that ordinary group returns and shared-replacement dependencies remain intact. The run-order CI fixture supplies the complete empty dorm interface; its two-pass task-retention regression passes. No additional glossary concept or lifecycle transition is introduced.


## Group Validation Boundary

[INV-SCHED-25] applies the existing ordinary fixed-working-primary requirement at static validation through `Operators.is_group_shift_anchor`. This replaces the separate, weaker shared-group and dormitory-group checks and removes the unreachable all-standby capacity fallback. No new state, helper or invariant identifier is introduced. Group and standby meanings remain unchanged; the glossary requires no edit. The active decision retains its lifecycle.

The [validation suite](../../../../arknights_mower/tests/standby_validation_capacity_tests.py) covers all-standby and zero-mood-worker groups with sufficient and insufficient beds, groups with and without dormitory members, additional bindings, combined backups and runtime rejection before live-state mutation. Ordinary and low-priority fixed workers permit the group; exhausted-shift and full-recovery requirements retain their existing precedence over standby. Ungrouped standby remains valid. Group-mood fixtures use real `Operator` instances to exercise the complete eligibility interface.

Review-repair verification passes 2431 focused cases across 37 test files, including the original bed protection and compensation regressions, group validation, backup admission, real group-mood fixtures and governance tests. Network and SQLite guards record zero access attempts; unrelated mastery reconciliation uses an offline substitute. All 33 Python files changed against alpha pass Ruff lint and formatting; structural governance and whitespace checks pass with the two existing archived-reference warnings. Two existing Pydantic fixture warnings remain. Standards and requirements review finds no remaining confirmed defect; live device execution is unverified.

The historical local backup replay removes Gravel’s obsolete all-zero-mood-worker group label in the loaded primary and backup plans, while retaining her workaholic setting, post and replacement. The original JSON snapshot and all eight replay assertions remain intact. Replay, group validation, group-mood and backup-rest suites pass 101 focused cases with zero network or SQLite access attempts; Ruff and formatting pass. The production group validation remains enforced.
