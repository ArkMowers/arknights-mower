---
title: Rescue Worker Rotation and Retry Ownership
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue Worker Rotation and Retry Ownership

## Contract

[INV-SCHED-09] preserves the next rescue retry when the active continuation finishes. Known zero mood permits initial rescue deployment; unknown readings, reservations and training protection remain blocking. Specialized crafting and mastery retain their own requirements.

Rescue grouping uses the effective roster and shared complete replacement matching [INV-SCHED-14]. A low-mood member triggers a complete group replacement, excluding configured zero-mood workers. Incomplete matching preserves the group. Displaced normal primaries join recovery demand; other workers remain reserved standby without bed requests.

## Simplification

The existing staffing task carries replacement assignments and reconciles actual occupants. The normal PlanConfig merge appends zero-mood worker and dormitory blacklist entries and overrides explicit dormitory order. The editor exposes these three existing settings without a new toggle. Worker eligibility returns a concrete blocking reason shared by planning and selection.

## Verification

Offline tests cover real dispatcher cleanup after deferred continuation, existing future wakeup reuse, zero and invalid card mood, measured-reading isolation, complete and incomplete group matching, original-primary recovery, zero-mood worker exemptions and independent settings persistence. No live-device tests or deployment occur.

## Standards Findings

The current executing task is not reused as its own successor. No second polling loop is introduced. Configuration and runtime episode state remain separate. Glossary changes have explicit user approval.

## Spec Findings

A failed staffing retry retains its one-minute continuation instead of sleeping until a distant dormitory release. Rescue standby does not consume normal-primary recovery beds. Actual observed occupants reconcile staffing before further planning.
