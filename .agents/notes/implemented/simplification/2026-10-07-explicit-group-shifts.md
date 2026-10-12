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

## Verification

Focused offline tests cover admission conflicts, common candidates, concurrent rest, ordered returns, failed execution, projection isolation, restart, backup transitions and training correction. No live device operations participate in verification.

## Standards Findings

PASS for code and automated governance. Projection state is isolated; task confirmation precedes live state changes; the runtime snapshot stores confirmed state and pending task targets. No device, network or deployment actions form part of verification. The bilingual glossary contains the wording explicitly approved by the user.

## Spec Findings

PASS. Same-cover groups rest concurrently, including admission within one pending plan and shared temporary beds. Different-cover groups remain mutually exclusive. Shared zero-mood primaries use no beds; ordinary shared primaries reserve one bed. Both return orders preserve the cover until the last group returns. Three-way intersections, multiple shared slots, queued returns, partial execution, restart and backup deferral have focused coverage. The perception arrangement retains Wang and Yu during correction; training Current placeholders reach the live reader. The focused scheduler suites verify 783 tests and 41 subtests; governance verifies 14 tests and four subtests.
