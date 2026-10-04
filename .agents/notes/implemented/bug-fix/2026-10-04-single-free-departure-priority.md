---
title: Single-Free Departure Priority
status: implemented
category: bug-fix
date: 2026-10-04
---

# Single-Free Departure Priority

## Contract

[INV-SCHED-20] requires one cross-dormitory single-target priority allocation when the resident leaves a dormitory containing only one effective Free bed. Existing residents and concurrent admissions compete through `resting_key`; equal ranks preserve existing positions. Multiple-Free dormitories retain ordinary admission behavior.

Queued arrangements, product reservations, protected residents and mandatory mood-limit completion remain authoritative. Future derived shift-on tasks do not reserve recovery positions; measured migration rebuilds their recovery deadlines. Projection never mutates actual positions, recovery markers or deadlines. Successful moves invalidate changed recovery assignments and read room recovery times through ordinary rearrangement.

## Implementation

Shift convergence allocates before applying the departure projection. Release checks occupant identity first and schedules rearrangement only for completed rooms, retaining partial-release retries. Ordinary mood updates do not create another allocation event.

## Verification

`dorm_single_free_departure_tests.py` covers cross-dormitory priority, recovery gaps, concurrent filling, reservations, release cancellation and partial completion. Focused admission, shift and release suites preserve existing boundaries. Tests perform no device or network I/O.

## Standards Findings

Pass: projection isolation, identity checks, bounded event allocation, explicit imports and focused offline verification. Glossary synchronization requires the exact wording approval specified by the root agent directives; the glossary files remain unchanged by this decision.

## Spec Findings

Pass: one effective Free bed is the departure trigger; all eligible dormitory residents compete through the shared priority key. Multi-Free departures, ordinary mood changes and protected or reserved positions retain their boundaries. The alpha-based focused run reports 468 passing tests, nine failures and four passing subtests. The same nine rescue failures reproduce on unmodified alpha; all 18 new departure tests pass. Ruff checks pass.
