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

Manager positions participate in recovery except the configured Fiammetta position. Reduced recovery demand restores available first manager positions across dormitories before second positions. Manager restoration never removes an unfinished recovery primary. Restoring a manager position does not perform an ordinary working-facility swap. Final handoff restores the normal dormitory layout together with working staffing.

## Observation and Scheduling Boundaries

History-derived targets and the insufficient-history fallback remain unchanged. Selection cards screen temporary working replacements using the personal normal shift-off threshold plus one; predictions do not establish standby or final-return eligibility. Unknown card mood does not qualify for temporary work, while low-mood primaries still qualify for recovery admission.

Strict personal-limit releases and their operation windows remain authoritative. Episode filling reserves unfinished and ready primaries until final handoff. Trade order operators remain reserved; eligible order runs, Fiammetta, crafting and mastery retain their existing specialized compensation. Ordinary orders and products are collected during mood checks with the existing cooldown. Temporary work changes only for incomplete arrangements, ineligible temporary workers or eligible specialized swaps; a primary reaching its target does not trigger working-facility rescoring.

## Verification

Offline tests cover individual admission for a group exceeding bed capacity, working-side complete replacement, manager-position capacity and restoration order, Fiammetta position retention, individual measured release, standby reservations and restart readback, stable temporary working combinations, and final target/native-feasibility handoff. Existing grouped staffing, strict-release, candidate-mood, processing and specialized compensation suites defend unchanged boundaries.

## Review

Standards Findings: the first independent snapshot review identifies stale departure reservations after restart and continued room traversal after cancellation. Both fixes retain measured target responsibility and stop cancelled execution. The second independent review verifies those fixes and identifies stale queued admission of a newly ready idle primary. Admission reconciliation now removes ready and departing members before every release early return; focused regressions preserve admission for an unfinished control. A fresh independent session reviews the repaired snapshot. The glossary retains its approved wording until the new exact bilingual replacement receives explicit user approval.

Spec Findings: thirteen focused offline suites pass 309 tests and four subtests after the queued-admission repair; a fresh independent review session remains pending. No live device validation is performed.
