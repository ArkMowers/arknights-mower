---
title: Rescue worker release and spare beds
status: implemented
category: bug-fix
date: 2026-10-06
---

# Rescue worker release and spare beds

## Contract and simplification

[INV-SCHED-09] compares rescue workers with their personal rescue thresholds before complete group replacement. Workers without replacements and configured zero-mood workers retain their existing behavior. [INV-SCHED-03] retains concrete staffing, departure and specialized reservations.

Episode standby tracking no longer creates a blanket dormitory reservation for workers named in the normal main plan, including its replacement lists. Ordinary spare-bed admission reuses shared candidates and priorities; normal primary recovery remains in episode targets. Rescue-only workers remain reserved standby. No additional recovery queue or cache is introduced.

## Verification and review

Offline regressions cover the exact rescue threshold, personal mood limits, complete group matching, normal replacement eligibility, rescue-only standby and specialized reservations. Standards review preserves shared matching and candidate selection. Specification review distinguishes eligibility for spare beds from guaranteed admission or an independent bed reservation.

Within an explicit priority tier, the planner compares at most 64 recovery combinations using the existing isolated handoff check. Remaining mood deficit ranks recovery effort when future-bed recovery rates are unavailable. This bounded search favors combinations that unblock exit without claiming a globally shortest recovery time or changing measured exit requirements. Regression tests cover multi-group combinations, normal fixed-bed exclusion, explicit priority and unchanged live observations.
