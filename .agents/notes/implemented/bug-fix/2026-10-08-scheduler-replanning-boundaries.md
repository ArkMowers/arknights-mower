---
title: Scheduler Replanning Boundaries
status: implemented
category: bug-fix
date: 2026-10-08
---

# Scheduler Replanning Boundaries

## Contract

[INV-SCHED-32] retains the first thirty-minute return window for unchanged recovery membership, position versions and staffing targets. [INV-SCHED-33] rejects arrangement targets beyond the current facility roster, including Current and other placeholders, while preserving the original task.

## Implementation

`plan_metadata` separates working mood predictions from the return window. Generated shift-on tasks carry the window start and recovery identity for their own members. Rebuilding, splitting and merging batches retain matching windows. New recovery episodes and changed targets establish new windows; full recovery and pending arrangement ordering retain their existing rules. Old tasks without window metadata initialize it on their next planning pass. Product-locked tasks keep their original objects and deadlines.

`agent_arrange_room` checks task length against the current roster before expanding Current or selecting operators. Any excess target, including Current, Free and empty placeholders, logs the facility, slot count and excess entries and stops automation without retry or task truncation. The roster length follows the configured facility plan; the error asks the user to check the main plan, backup task and in-game facility slots.

Simplification inspection keeps both corrections at existing planning and placeholder-resolution boundaries. No new dependency, configuration switch, planner or external device operation is added. The window metadata is bounded by the task roster and uses existing recovery position versions.

## Verification

Offline tests cover repeated replanning at the reported times, overdue execution, earlier mood predictions, measured mood refreshes, new recovery episodes, changed targets, full recovery, batch splitting and merging, pending arrangements and locked product tasks. Facility tests cover excess named operators and placeholders with populated and cleared caches, preserve invalid tasks and verify successful arrangement after the extra entry is removed. The supplied schedule QR codes confirm that the main room_1_3 roster contains Ulpianus and Specter, while the Deep Sea forced-work backup task adds a third Current. This configuration matches the two-slot room and three-entry task in the local recording and reproduces the placeholder failure. The screenshot has no traceback, so this evidence does not establish that every reported IndexError has this cause.

## Standards Findings

PASS: Existing recovery identities, projection boundaries, resource reservations and facility roster reads remain authoritative. The invariants are registered in all three governance locations.

## Spec Findings

PASS: Clock advancement alone does not restart the return wait. Excess named operators and placeholders stop automation with a visible error; the original task remains intact and does not repeat room entry.
