---
title: Manual dormitory priority
status: implemented
category: feature
date: 2026-10-08
---

# Manual dormitory priority

## Contract and simplification

[INV-SCHED-20] supports interleaving each dormitory's high-priority bed and low-priority beds. Default selections remain 1, 2, 3, 4. Optional low-priority entries are user-selected; omitted low-priority beds remain usable at the end. The first effective Free position is the high-priority bed, including projected group transitions. Beds within one low-priority entry follow physical slot order.

The existing `dorm_order` field carries this ordering through main, backup and rescue plans. `effective_dorm_order` replaces duplicated room-only normalization in runtime initialization and configuration migration, preserving legacy room order and new low-priority entries. No extra configuration field or recovery-rate calculation is introduced.

`Operators.ordered_dorms` derives an allocation view without changing stored bed records. New admissions, idle filling and required relocation share that view. Explicit options determine the selected beds instead of automatic single-target-first allocation. Isolation exchanges equally ranked new occupants between selected non-target beds without changing the bed set or recovery ranking. Recovery tiers and reservations remain authoritative. Existing residents retain valid positions; only new arrivals can initiate strictly-lower-tier preemption. Changing priority alone does not generate moves.

## Verification and review

Offline tests cover default selections, explicit low options before another dormitory or their own high option, configuration round trips, backup inheritance, admission tiers, projected Free activation, preserved capacity and residents, preemption, reservations and isolation within the selected beds, including protection for different recovery ranks and existing residents. Vue tests cover eight available options with four selected defaults and retained edit locks.

Standards review reuses the existing configuration, projection and reservation boundaries. Specification review preserves the four default selections and exposes low-priority options only for manual selection. Existing recovery skill recognition remains unchanged.
