---
title: Protected Dormitory Bed Tiers
status: implemented
category: bug-fix
date: 2026-10-09
---

# Protected Dormitory Bed Tiers

## Contract

[INV-SCHED-42] protects occupied recovery beds of explicit-priority operators, normal primaries, low-priority primaries and priority replacements. These four tiers displace standby primaries, ordinary replacements and idle operators. Standby primaries displace ordinary replacements and idle operators, and ordinary replacements displace idle operators, only with valid current mood no greater than 80% of their own mood upper limit. Same-tier takeovers remain denied. Completion predictions, expired deadlines and rescue mode do not bypass occupancy protection. Vacant-bed ranking and single-target position allocation retain their existing order. Ordinary returns, ordinary full-mood releases, mandatory personal-limit departures and explicit staffing tasks retain their own admission.

## Simplification Preflight

`Operators._slot_takable`, `try_add_release_dorm` and `preserve_resting_crafters` share the recovery tier enum but bypass one another for completed residents. One shared predicate expresses occupancy protection and the applicant mood threshold across all three callers; no new configuration, task type or persisted state is introduced. Automatic named fill tasks use the existing planner for dispatch validation.

## Cause and Scope

Commit `0cb1e21f7a58050999a8cb874827042defb967a1` removes the primary-resident protection barrier and permits any strictly higher tier to take over a bed. This correction restores the barrier and includes priority replacements in the protected tiers. [The previous priority decision](../../implemented/simplification/2026-10-02-priority-aware-dorm-recovery.md) retains its other recovery and reservation contracts; this record supersedes its unrestricted tier takeover rule.

## Verification

[Focused regressions](../../../../arknights_mower/tests/protected_dorm_bed_tiers_tests.py) cover occupied-bed protection, completed and unknown readings, expired deadlines, planning and Free selection, automatic named dispatch, and legal lower-tier takeovers at 80% of personal mood limits of 12, 20 and 24. A standby applicant above the threshold does not block a later eligible replacement; queued named fills recheck the applicant mood before dispatch. Tier matrices cover ordinary and rescue admission. Device inputs, live network and workspace databases are excluded.

## Dispatch and Compensation

Only unstarted automatic `NOT_SPECIFIC` and `FILL_DORM` tasks carrying `dorm_fill_plan` are rebuilt. Room retries, recovery restoration, locked product and active backup shifts, mandatory releases and emergency staffing retain their existing lifecycle. Rebuilding preserves task identity and reevaluates critical-task admission before fallback writes, live compensation and device input.

A standby departure retains any protected working group member still resting, including a completed member; the ordinary group return task governs its later return. Completed fixed managers in temporarily opened emergency slots use the existing manager-departure projection before bed admission. Explicitly prioritized managers remain protected. Neither operation introduces a generic recovery takeover exception.

## Review and Results

Standards axis: no remaining confirmed findings; the shared predicate has three production callers, projections isolate mutable beds and tasks, and the glossary additions use the wording explicitly approved by the user.

Requirements axis: the full tier matrices, 232 focused protection and mood-threshold cases, legal standby departures, normal and merged full-mood releases, mandatory personal limits, queued named fills and RUN_ORDER/SWAP_SUPPORT admission satisfy [INV-SCHED-42]. The two focused batches pass 1145 and 309 tests. Network and SQLite guards report zero attempted accesses; unrelated history, inventory and mastery observers use offline substitutes. Device selection uses offline doubles. Real game execution is outside this verification.

The structural governance gate, 25 governance tests and 21 subtests pass. Ruff checks and formatting pass for all 16 changed Python files. Two archived-note reference warnings predate this change.
