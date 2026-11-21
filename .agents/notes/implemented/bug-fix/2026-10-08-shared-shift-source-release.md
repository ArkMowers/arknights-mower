---
title: Shared Shift Dispatch and Confirmation
status: implemented
category: bug-fix
date: 2026-10-08
---

# Shared Shift Dispatch and Confirmation

## Contract

[INV-SCHED-25] Shared replacement matching includes primary positions released by the same arrangement. Release eligibility requires the source shared primary to occupy its own participating position and to leave under the projected group state. Every destination still needs a complete unique replacement assignment. Explicit backup slots retain control of their occupants. Concrete dormitory replacements remain fixed posts; only explicit `Free` replacements open dynamic beds.

Conflicting arrangements remain outside dispatch until their blocking groups confirm return and replacement matching succeeds. Training slots skipped by execution or mastery protection do not become repeated group-confirmation targets. All remaining targets require actual observation; an arrangement whose only group anchors are skipped commits no group transition.

## Implementation

`normalize_shared_arrangement` collects participating shared positions before matching. A primary leaving one of those positions is eligible for a compatible same-group dormitory replacement even when its source replacement has not yet been written into the input plan. Incomplete matching leaves the caller's plan and live positions unchanged. The existing matching supplies the guarantee without a separate source-reservation model.

`_suspend_group_shift` moves an incompatible task to `waiting_group_shifts`, outside the timed dispatch queue and its replacement and bed reservations. Return-task rebuilding proceeds independently. `_resume_waiting_group_shifts` retains it while any recorded blocking group remains resting, then verifies complete matching against current positions and reservations before requeuing it once. Forecast deadlines neither wake nor repeatedly postpone the task. Normal scheduler state changes trigger cached revalidation without device polling. Startup observation and automatic rescue prevent premature resumption. State snapshots persist suspended tasks and their blocking groups.

`agent_arrange_room` owns the live training observation. With automatic mastery enabled, active mastery or observed protection excludes the entire training room when assistant following is disabled; following permits the assistant target and excludes the trainee target. With automatic mastery disabled, the assistant follows the Scheduling Plan regardless of assistant following or mastery protection. Live training, pending collection and unreadable room state skip only the trainee; an idle trainee follows ordinary staffing. No mastery reconciliation or collection runs while disabled.

The current task carries at most two skipped training-slot indices. `_complete_group_shift` excludes these indices from remembered targets before applying the existing mastery policy and calculating remaining group transitions. Confirmation reuses its existing target model without another room read or a disabled-mastery protection snapshot. Missing targets in other rooms still retain the task. A transition supported only by excluded training anchors is discarded, preserving confirmed group state. This extends [INV-SCHED-25] without another invariant or protection-policy implementation.

## Verification

Offline regressions cover both position traversal orders, full shift projection, an unavailable source cover, unchanged live state, fixed dormitory replacement identity, two confirmed group returns, overdue forecast times, unavailable replacements after return, dispatch suspension, restart snapshots, and queue rebuilds. Training tests cover single-group members, database and queued mastery plans, observed training, assistant following, incomplete ordinary-room confirmation, skipped-only transitions, and the actual training execution gate. A replay reconstructed from the supplied schedule and observed occupants verifies the final training assistants and fixed dormitory replacement. No live device or configuration is changed.

Manual-training regressions cover both assistant-following settings, training, pending collection, unreadable and idle states, ignored assistant protection, actual assistant selection, preserved trainee occupancy, incomplete ordinary-room confirmation and skipped-only group transitions. Six focused scheduling and mastery suites plus governance tests pass 329 tests. Ruff and structural governance checks pass. Assistant and trainee identities and their relationship to the Scheduling Plan retain their glossary meanings; this repair changes execution and confirmation rules, so no glossary edit is necessary.
