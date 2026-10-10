---
title: Shared Shift Dispatch and Confirmation
status: implemented
category: bug-fix
date: 2026-10-08
---

# Shared Shift Dispatch and Confirmation

## Contract

[INV-SCHED-25] Shared replacement matching includes primary positions released by the same arrangement. Release eligibility requires the source shared primary to occupy its own participating position and to leave under the projected group state. Every destination still needs a complete unique replacement assignment. Explicit backup slots retain control of their occupants. Concrete dormitory replacements remain fixed posts; only explicit `Free` replacements open dynamic beds.

Conflicting arrangements remain outside dispatch until their blocking groups confirm return and replacement matching succeeds. Mastery-protected training slots do not become repeated group-confirmation targets. All remaining targets require actual observation; an arrangement whose only group anchors are protected commits no group transition.

## Implementation

`normalize_shared_arrangement` collects participating shared positions before matching. A primary leaving one of those positions is eligible for a compatible same-group dormitory replacement even when its source replacement has not yet been written into the input plan. Incomplete matching leaves the caller's plan and live positions unchanged. The existing matching supplies the guarantee without a separate source-reservation model.

`_suspend_group_shift` moves an incompatible task to `waiting_group_shifts`, outside the timed dispatch queue and its replacement and bed reservations. Return-task rebuilding proceeds independently. `_resume_waiting_group_shifts` retains it while any recorded blocking group remains resting, then verifies complete matching against current positions and reservations before requeuing it once. Forecast deadlines neither wake nor repeatedly postpone the task. Normal scheduler state changes trigger cached revalidation without device polling. Startup observation and automatic rescue prevent premature resumption. State snapshots persist suspended tasks and their blocking groups.

`_complete_group_shift` applies the existing training correction protection to the remembered confirmation targets. Active mastery or observed protection excludes the entire training room when assistant following is disabled; following permits the assistant target and excludes the trainee target. Missing targets in other rooms still retain the task. A transition supported only by excluded training anchors is discarded, preserving the confirmed group state. This uses existing protection policy without new candidate-occupancy checks.

## Verification

Offline regressions cover both position traversal orders, full shift projection, an unavailable source cover, unchanged live state, fixed dormitory replacement identity, two confirmed group returns, overdue forecast times, unavailable replacements after return, dispatch suspension, restart snapshots, and queue rebuilds. Training tests cover single-group members, database and queued mastery plans, observed training, assistant following, incomplete ordinary-room confirmation, skipped-only transitions, and the actual training execution gate. A replay reconstructed from the supplied schedule and observed occupants verifies the final training assistants and fixed dormitory replacement. No live device or configuration is changed.
