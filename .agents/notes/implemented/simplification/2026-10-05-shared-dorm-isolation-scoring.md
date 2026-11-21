---
title: Shared Dormitory Isolation Scoring
status: implemented
category: simplification
date: 2026-10-05
---

# Shared Dormitory Isolation Scoring

## Contract

[INV-SCHED-23] keeps dormitory isolation inside admission projection, subordinate to recovery priority and bed ownership.

## Simplification

Primary group allocation, ordinary vacancy filling and intelligent rescue share `Operators.dorm_isolation_cost`. The score counts same-group roommates from observed occupancy, existing bed reservations and explicit projected arrangements. One score replaces separate isolation policies at these three admission boundaries. The existing `_slot_takable` and recovery ranking remain authoritative.

`plan_dorm_isolation` refines projected new arrivals after normal single-target allocation. Fixed manager positions, the first effective recovery bed in each dormitory, existing residents and reserved positions remain fixed. Only swaps or vacant-bed moves that reduce same-group roommate pairs are accepted. Selection and correction do not introduce a second isolation policy.

## Verification

Focused tests cover unlimited configuration, overlapping groups, reservations, ordinary vacancy capacity, intelligent rescue, single-bed ownership and complete pre-submission shift projection.
