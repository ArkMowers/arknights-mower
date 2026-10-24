---
title: Dormitory Vacancy Priority
status: archived
category: simplification
date: 2026-10-12
---

# Dormitory Vacancy Priority

The [stable dormitory recovery order](../../implemented/bug-fix/2026-10-12-stable-dorm-recovery-order.md) supersedes this allocation policy; the remainder records the historical implementation.

## Contract

[INV-SCHED-20] preserves existing single-target residents and ranks movable vacancy candidates by recovery tier, mood deficit and configured dormitory order, defaulting to 1, 2, 3, 4. Admission and departure events trigger allocation; mood changes alone do not relocate residents. Reservations, fixed replacement positions and protected residents remain authoritative.

## Implementation

`prioritize_new_dorm_recovery` uses configured room order for eligible beds and removes locality from vacancy candidate ranking. The ordinary idle crafting permutation remains confined to its existing tier. Existing target preemption still requires a strictly higher tier. Projection does not mutate measured mood, actual occupancy or recovery markers; actual relocation retains recovery confirmation and fresh timing observations.

Pre-flight inspection identifies one unused local `get_ranking` helper in `try_reorder`, with no callers. Removing it and the vacancy locality partition keeps allocation in its existing shared function without adding configuration or a second planner.

## Verification

Offline regressions cover a local Standby or Low Main Minimalist arrival competing with a lower-mood Low Main Eunectes rear resident while an existing Main Greyy the Lightningbearer target remains fixed. Equal-tier and equal-deficit candidates follow default and custom room order even with stale bed list order. Existing admission, departure, reservation, projection and crafting tests verify the retained boundaries.

## Standards Findings

PASS: Projection isolation, reservations, fixed replacement positions and actual recovery confirmation remain intact. Approved glossary wording and [INV-SCHED-20] are synchronized across the governance locations.

## Spec Findings

PASS: All 383 focused tests pass, including vacancy ordering, existing target retention, admission preemption, recovery confirmation, configuration migration, crafting order and governance fixtures. Lint, documentation links and glossary checks pass. The migration suite emits one Pydantic serializer warning.
