---
title: Explicit Group Shift State
status: implemented
category: simplification
date: 2026-10-07
---

# Explicit Group Shift State

## Contract

[INV-SCHED-25] Each group records its confirmed shift state. Shared primaries use replacements compatible with every resting binding; incompatible groups wait. A return retains the replacement until the final dependent group returns. Planning and projections do not commit live group state.

## Simplification

Dispatch, return planning and occupancy projection share one group-state map and a replacement intersection. The three former `select_arrangement_bindings` callers use the explicit transition API; `group_is_resting` reads confirmed state and limits position inference to unknown legacy groups. The active binding remains a compatibility adapter for existing bed and replacement helpers; it no longer decides which group is resting. This change adds state confirmation and removes speculative ownership changes from successful planning.

The common `_prepare_group_shift` boundary completes ordinary state-changing targets before either full convergence or a fast path executes. This closes the gap between group-owned state and a task containing only one member. Missing departures reuse the existing matching and bed planner on an isolated projection; no second allocation algorithm is introduced. Exact-slot covers qualify regardless of binding count. Slot correction and genuine group return use separate inputs to same-cycle departure protection. Training-only adjustments, protected training slots, explicit backup staffing and standby membership retain their existing boundaries. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md#211-multiple-group-bindings) owns these operational details.

Confirmation dependencies reuse the suspended queue instead of changing a task's time by one minute. References to started predecessors survive the existing snapshot format. Only overlapping groups, shared slots and staffing resources block dispatch; distinct shared slots do not create a dependency through another group. Failed confirmation retains the dependency, and successful confirmation revalidates and releases it at the same completion boundary. Independent started shifts retain their combined pending recovery context. This refinement reuses [INV-SCHED-25], [INV-SCHED-14] and [INV-SCHED-39]; group and task concepts remain unchanged.

## Verification

Focused offline tests cover admission conflicts, common candidates, concurrent rest, ordered returns, failed execution, projection isolation, restart, backup transitions and training correction. No live device operations participate in verification.

`ordinary_group_shift_tests.py` exercises the production preparation/convergence/confirmation sequence. Its initial eight cases produced four failures and four passes on the pre-repair version: exact-slot matching, correction-triggered departure, a Fiammetta fast-path return and unrelated confirmation admission exposed the missing boundaries. Additional cases cover incomplete departures, predecessor failure, snapshot identity, immediate release without timestamp changes, distinct shared slots, combined pending context and the correction sequence that releases a contested cover before whole-group departure. Training-protection cases confirm that completing ordinary targets does not wait for a protected trainee or discard the assistant's independent policy. Verification is offline; actual device timing remains unmeasured.

The completed repair passes 1,221 tests across 31 focused group, shift, backup, training and failure-retention suites, with eight existing Pydantic serialization warnings. Ruff, formatting and diff-whitespace checks pass. Governance against the PR comparison base passes its three structural gates, retaining two historical archived-reference warnings; these structural results do not replace behavior verification or contract review.

## Standards Findings

PASS for code and automated governance. Projection state is isolated; task confirmation precedes live state changes; the runtime snapshot stores confirmed state and pending task targets. No device, network or deployment actions form part of verification. The bilingual glossary contains the wording explicitly approved by the user.

## Spec Findings

PASS. Same-cover groups rest concurrently, including admission within one pending plan and shared temporary beds. Different-cover groups remain mutually exclusive. Shared zero-mood primaries use no beds; ordinary shared primaries reserve one bed. Both return orders preserve the cover until the last group returns. Three-way intersections, multiple shared slots, queued returns, partial execution, restart and backup deferral have focused coverage. The perception arrangement retains Wang and Yu during correction; training Current placeholders reach the live reader. The focused scheduler suites verify 783 tests and 41 subtests; governance verifies 14 tests and four subtests.
