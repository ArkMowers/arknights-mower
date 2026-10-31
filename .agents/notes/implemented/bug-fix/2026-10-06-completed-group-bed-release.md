---
title: Completed Group Bed Release
status: implemented
category: bug-fix
date: 2026-10-06
---

# Completed Group Bed Release

## Contract

[INV-SCHED-21] keeps personal completed departures separate from ordinary group returns. A resident with valid mood at their personal recovery cap may yield a bed and remain idle while unfinished required group members retain beds. The existing group return task is preserved. Unknown mood or an expired bed timer alone does not establish completion.

## Implementation

The existing displacement compensation shares its standby branch with completed residents. No new task type, reservation or configuration is introduced. All-completed groups and displaced unfinished required residents retain existing return handling. Ordinary return-time calculation remains unchanged.

## Verification

Offline tests cover high and low priority, both idle-release settings, preservation of the queued return deadline, return planning after room readback, unknown mood and expired timers. Seven related suites pass 498 tests and 6 subtests.

## Standards Findings

Pass: shared compensation branch, isolated projection, existing recovery-cap semantics and focused offline tests.

## Spec Findings

Pass: ordinary filling cannot prematurely recall unfinished group members merely because another member completed recovery. Normal group return remains independently scheduled.
