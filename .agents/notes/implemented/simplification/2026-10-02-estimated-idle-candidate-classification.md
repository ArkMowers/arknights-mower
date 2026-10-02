---
title: Estimated Idle Candidate Classification
status: implemented
category: simplification
date: 2026-10-02
---

# Estimated Idle Candidate Classification

## Contract

The shared `DormCandidates` snapshot identifies eligible unknown candidates with a valid low selection-card estimate separately from measured recovery candidates. Scanning, ordinary replacement planning and selection consume that classification. Estimates retain their existing expiry, eligibility and measured-mood isolation under [INV-SCHED-15].

## Simplification Evidence

`_plan_primary_recovery` repeats the estimate threshold check while `try_add_release_dorm` and `dorm_mood_fallback_candidates` consume only measured recovery or generic unknown states. Computing the low-estimate subset once in `dorm_candidates` replaces the planner's separate threshold loop and supplies both admission and selection with the same snapshot. No persistent flags or device scans are added.

The [replacement decision](../bug-fix/2026-10-02-estimated-idle-replacement.md) defines the behavior and focused tests. Existing glossary definitions already permit selection-card screening without establishing measured recovery.
