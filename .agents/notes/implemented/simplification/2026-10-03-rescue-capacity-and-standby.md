---
title: Rescue Capacity and Standby
status: implemented
category: simplification
date: 2026-10-03
---

# Rescue Capacity and Standby

## Contract

[INV-SCHED-09] separates working-group replacement from individual dormitory recovery. A bound working group leaves its frozen primary positions after complete automatic skill-based replacement succeeds. Dormitory capacity does not impose complete-group admission: individual recovery needs and shared priority select available beds. Configured manager positions provide episode-local recovery capacity; Fiammetta retains her configured position.

A primary with a measured recovery target leaves the dormitory into reserved standby. That primary remains reserved from temporary working assignments and ordinary dormitory filling until final handoff. Other group members continue recovering. Target completion neither restores a primary working position nor rescores temporary working combinations. All required targets and native rotation feasibility permit unified restoration under the schedule selected during final handoff; backup transitions remain frozen until then.

## Simplification Evidence

Removing the single-caller `_emergency_return_groups` separates individual measured readiness from final working return, native projection and temporary staffing rescoring. Individual target release reuses dormitory arrangement and stores `ready_members`; final handoff remains the single primary-return boundary. Existing temporary staffing rescoring remains available for rejected working candidates rather than running after each completed recovery.

The shared `emergency_dorm_plan` allocates explicit individual recovery needs with shared candidates, reservations and priorities. It has no complete-group bed admission or all-bed rollback. The normal shift planner retains complete group beds; the exception applies only during intelligent rescue. Manager capacity uses an episode-local layout, preserving the configured layout for final restoration. No unpublished-state compatibility, new setting, personal zero-mood exemption or independent collection timer is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the current interface guarantees.

## Recovery Capacity

Unfinished recovery primaries use available beds by individual need and shared priority. Capacity shortage queues remaining recovery needs instead of rejecting a complete working-group replacement. Ready primaries release beds independently and retain measured target responsibility in `ready_members` across partial arrangements and restart. Actual occupancy confirms completed departures; an uncompleted physical departure keeps its bed identity and reservation.

Manager positions participate in recovery except the configured Fiammetta position. Reduced recovery demand restores at most one configured dormitory group-recovery or shared-recovery manager per dormitory, including Bingniang, to unneeded capacity. After group restoration across dormitories, remaining spare capacity permits one configured single-target manager per dormitory with a restored group manager. Self-recovery managers leave those positions open. Manager restoration never removes an unfinished recovery primary. Restoring a manager position does not perform an ordinary working-facility swap. Final handoff restores the normal dormitory layout together with working staffing.

## Observation and Scheduling Boundaries

History-derived targets and the insufficient-history fallback remain unchanged. Selection cards screen temporary working replacements using the personal normal shift-off threshold plus one; predictions do not establish standby or final-return eligibility. Unknown card mood does not qualify for temporary work, while low-mood primaries still qualify for recovery admission.

Strict personal-limit releases and their operation windows remain authoritative. Episode filling reserves unfinished and ready primaries until final handoff. Trade order operators remain reserved; eligible order runs, Fiammetta, crafting and mastery retain their existing specialized compensation. Ordinary orders and products are collected during mood checks with the existing cooldown. Temporary work changes only for incomplete arrangements, ineligible temporary workers or eligible specialized swaps; a primary reaching its target does not trigger working-facility rescoring.

## Verification

Offline tests cover individual admission for a group exceeding bed capacity, working-side complete replacement, manager-position capacity and group-recovery eligibility, Fiammetta position retention, individual measured release, standby reservations and restart readback, stable temporary working combinations, and final target/native-feasibility handoff. Existing grouped staffing, strict-release, candidate-mood, processing and specialized compensation suites defend unchanged boundaries.

## Review

Standards Findings: the first independent snapshot review identifies stale departure reservations after restart and continued room traversal after cancellation. Both fixes retain measured target responsibility and stop cancelled execution. The second independent review verifies those fixes and identifies stale queued admission of a newly ready idle primary. Admission reconciliation now removes ready and departing members before every release early return; focused regressions preserve admission for an unfinished control. The final independent session reviews snapshot `08dca8e58a621d30e537c1e725571ad2eaf24ffc` and reports Standards Findings PASS and Spec Findings PASS without actionable findings in the scoped changes. The glossary contains the explicitly approved bilingual replacement for individual admission, reserved standby and spare-capacity manager restoration.

Spec Findings: PASS. Thirteen focused offline suites pass 309 tests and four subtests after the queued-admission repair. Final independent verification passes 337 tests and four subtests, including three new real-dispatch and selection-entry controls; the three governance gates pass. The test sets overlap and are not added together. Local merged-source regressions pass 40 tests while preserving the existing branch, HEAD, index and unrelated edits. No live device validation is performed.

The independent alpha-merge review of snapshot `59076096cc01831e5e89319bc3708a43aea85922` reports Standards Findings PASS and Spec Findings PASS. Thirty focused offline suites pass 994 tests and 21 subtests; governance and scoped production Ruff checks pass. Conflict resolution preserves the incoming candidate-consistency rule and the intelligent-rescue individual-capacity exception. The merged local source passes 371 focused tests and 11 subtests after adopting alpha's one-minute training handoff allowance. These test sets overlap earlier verification and are not added together.
