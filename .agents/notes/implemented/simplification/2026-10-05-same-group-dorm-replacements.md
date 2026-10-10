---
title: Shared Same-Group Dormitory Replacements
status: implemented
category: simplification
date: 2026-10-05
---

# Shared Same-Group Dormitory Replacements

## Contract

[INV-SCHED-22] permits primary-to-primary replacement between distinct primaries in the same nonempty group when at least one is a grouped dormitory primary, preserves their primary identities and requires a complete arrangement before movement. Replacements between two working primaries are prohibited. Ordinary idle replacements retain existing eligibility. Dormitory-primary exchanges retain fixed staffing identity without creating recovery records or reducing required working beds. Fixed dormitory positions occupied by their configured same-group working replacements record recovery and group return timing without becoming Free capacity. Grouped dormitory members neither trigger exhaustion nor require additional recovery beds. Reservations, mood limits, training protection and single-target recovery confirmation remain binding.

## Simplification

Validation, exhausted support and correction share one same-group replacement predicate instead of duplicating primary exclusions. Existing `group_dorm`, occupancy projection, replacement matching, readback and group return paths provide fixed recovery bookkeeping; no configuration switch or independent rotation mechanism is added. Replacement matching retains configured preference when beds suffice and seeds a maximum fixed-recovery matching when dynamic beds are insufficient. Unchanged projected positions preserve single-target confirmation; actual target or provider movement invalidates it.

## Verification

`same_group_dorm_replacement_tests.py` covers working/dormitory replacements in both directions, same-room and cross-room dormitory-primary exchanges, ordinary idle covers, invalid group and facility relationships, complete matching, fixed and dynamic recovery, actual-state isolation, return timing, correction, exhausted support, reservations, personal limits and single-target recovery.

The submitted recruitment group validates with both an ordinary idle dormitory replacement and a reciprocal working/dormitory-primary replacement. The focused scheduling and governance suites pass 566 tests and four subtests. The existing Pydantic fixture emits one serialization warning. Verification uses mocked room confirmation and readback; no live device test runs.

## Standards Findings

PASS: Shared replacement validation preserves primary identity, mutable projections isolate fixed recovery records, failed matching preserves occupancy, and mandatory personal limits and reservations remain binding. The approved glossary addition, invariant registrations, bilingual triplet and governance gates pass.

## Spec Findings

PASS: Ordinary idle replacements remain eligible; different or empty groups, working-to-working primary replacements and self-replacement fail validation. Fixed recovery positions participate in normal and exhausted rotations, correction, countdown readback, snapshot restoration and whole-group return without becoming Free capacity. Low or unknown ordinary dormitory replacements compete during single-target setup; only actual safe readback records confirmation.
