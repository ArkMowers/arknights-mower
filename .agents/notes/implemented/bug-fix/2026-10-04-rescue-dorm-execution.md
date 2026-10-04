---
title: Rescue Dormitory Execution
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue Dormitory Execution

## Contract

[INV-SCHED-09] synchronizes completed staffing reservations before dormitory planning. Recovery primaries become eligible in the same scheduling pass. [INV-SCHED-03] compares departures against the game's compacted occupant order rather than an interior vacant slot.

## Simplification

Initial dormitory allocation and measured-ready release share vacancy normalization. Explicit vacancies remain vacant during rescue dormitory selection. Fiammetta retains her position through ordinary filling before her fixed slot when necessary.

## Verification

Offline regressions cover staffing reservation removal before initial bed selection, middle-bed departure, Fiammetta's position, exception and incomplete-release retries before a distant order. Existing partial-release tests retain observed progress.

## Standards Findings

No new polling loop or configuration is added. The existing continuation persists pending releases and restores the calling task after exceptions.

## Spec Findings

Failed or incomplete departures retain a one-minute continuation. Pending departures stop subsequent planning; actual departure takes precedence over an arrangement return value.
