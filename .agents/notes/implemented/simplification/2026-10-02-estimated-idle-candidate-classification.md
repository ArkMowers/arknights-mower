---
title: Estimated Idle Candidate Classification
status: implemented
category: simplification
date: 2026-10-02
---

# Estimated Idle Candidate Classification

## Contract

The shared `DormCandidates` snapshot identifies eligible unknown candidates with a valid low selection-card estimate separately from measured recovery candidates. Scanning, vacancy filling and selection consume that classification. Estimates retain their existing expiry, eligibility and measured-mood isolation under [INV-SCHED-15]. Occupied-bed admission follows [INV-SCHED-43]: the estimated subset alone grants no replacement permission or full-occupancy retention override.

## Simplification Evidence

`dorm_candidates` computes the low-estimate subset once for `_plan_primary_recovery`, `try_add_release_dorm` and `dorm_mood_fallback_candidates`. The shared snapshot removes repeated estimate classification without granting independent takeover rights. The replacement planner admits estimated candidates in the first four protected tiers only through legal lower-tier takeover; other estimated candidates wait for vacancy admission. No persistent flags or device scans are added.

The [replacement decision](../bug-fix/2026-10-02-estimated-idle-replacement.md) defines the behavior and focused tests. Existing glossary definitions already permit selection-card screening without establishing measured recovery.
