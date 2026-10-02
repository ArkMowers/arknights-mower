---
title: Estimated Idle Replacement
status: implemented
category: bug-fix
date: 2026-10-02
---

# Estimated Idle Replacement

## Contract

[INV-SCHED-13] requires eligible low selection-card estimates to permit replacing completed ordinary residents despite previous full-occupancy retention or exhausted-search flags. Unknown candidates remain subject to selection-page confirmation; estimates never establish measured mood or recovery deadlines. Unfinished residents, idle-release exclusions, reservations and mandatory personal limits retain their existing rules.

## Failure Boundary

A low card estimate suppresses another physical scan, but the ordinary replacement planner has no measured recovering candidate and skips residents marked for full-occupancy fallback. An exhausted search independently blocks unknown selection and resolves an already queued Free slot back to its full resident, causing the room to be skipped as unchanged. The retained resident then blocks later replacement planning despite an eligible low card candidate. The shared estimate subset connects those decisions without clearing unrelated estimates or residents.

The [classification audit](../simplification/2026-10-02-estimated-idle-candidate-classification.md) records the simplification. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent behavior. Existing glossary definitions remain accurate.

## Verification

Offline tests reproduce registered and unregistered low-card candidates with active and exhausted search, normal planning without a new scan, actual selection and low-mood readback. Negative cases cover expired, future and full estimates, working and reserved candidates, blacklists, mandatory limits and unfinished residents. Planning preserves operator samples and bed deadlines. The real dormitory 3 arrangement entry confirms replacement rather than skipping an unchanged roster, for registered and unregistered candidates with active or exhausted search.
