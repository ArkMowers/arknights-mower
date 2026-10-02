---
title: Intelligent Rescue Observation Budget
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Observation Budget

## Contract

[INV-SCHED-07] applies shared recovery tiers to emergency beds. The [manager admission decision](../simplification/2026-10-02-emergency-manager-admission.md) defines measured-completed manager admission independently of configured priority.

[INV-SCHED-03] applies the existing strict-release operation allowance before collection and each room observation. Pending room identities persist after completed reads and survive restart. Deferred observations advance the existing rescue check and authorize no staffing, target or exit decision. A collection performed before a partial observation is not repeated during continuation; cooldown-only calls reserve no collection time.

[INV-SCHED-09] keeps handoff observation pending after arrangement until all rooms are read. Resumed handoff reinstates the normal dormitory plan, retains specialized restoration obligations and rechecks measured eligibility and native feasibility. Lost feasibility returns the episode to recovery without repeating completed staffing scans.

## Simplification

Emergency bed admission uses the existing shared takeover predicate. Scan, collection, readback and arrangement share one operation-budget predicate. Pre-arrangement and final observation share one native-feasibility check. Observation progress and final handoff remain fields of the existing episode state, with no new setting or compatibility path. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the interface guarantees.

## Verification

Offline tests retain the real bed planner, Current-slot resolution, selection, strict-release generation and read loop. Virtual time covers partial batches, persisted restarts, completed and predicted managers, explicit priority, collection time and measured room allowances. Deferred handoff tests retain actual feasibility and specialized restoration boundaries. Device and storage boundaries are isolated.

## Review

Standards Findings: shared tier admission and timing predicates retain existing reservations and bounded device operations.

Spec Findings: completed managers yield beds; other resident priority stays effective; partial observation cannot steal mandatory release time or authorize an early exit. The isolated-context review evaluates the committed snapshot. No live-device integration tests run.

Fifteen focused offline suites pass 794 tests and 30 subtests. Scoped Ruff, formatting, whitespace and all governance gates pass.
