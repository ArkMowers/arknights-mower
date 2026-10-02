---
title: Emergency Collection Coalescing
status: implemented
category: simplification
date: 2026-10-02
---

# Emergency Collection Coalescing

## Contract

[INV-SCHED-09] collects ordinary orders and products when an assisted-recovery mood check is due. Collection never advances the next mood check. Paused order operators do not suppress collection, and collection precedes a ready handoff. The existing ordinary collection cooldown prevents repeated collection during short mood-check intervals.

`EmergencyRecoveryMixin._emergency_tick` is the single assisted-collection caller. Startup, check-task dispatch and post-task processing share that due-observation gate. Pending checks use `next_read`. Specialized task appointments retain their own scheduling.

## Simplification and Review

The three separate collection callers become one, and the independent collection deadline is removed. The [assisted recovery contract](../../implemented/simplification/2026-10-02-maa-assisted-emergency.md) retains the remaining recovery boundaries.

Standards Findings: collection reuses the existing side-effect boundary and persisted mood-check timestamp. No configuration or glossary definition changes are required.

Spec Findings: a thirty-minute mood check cannot create a fifteen-minute collection wakeup; missing or overdue collection history preserves this rule. Due mood checks still collect when order runs are paused.

Verification: five focused offline suites pass 337 tests and 20 subtests, covering delayed observations, due collection, paused orders, startup reconciliation and handoff.
