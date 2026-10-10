---
title: Rescue managers before fillers
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue managers before fillers

## Contract and simplification

[INV-SCHED-09] restores available group-recovery managers before single-target managers, and both before ordinary replacements. An unavailable or unconfigured group manager does not prevent single-target restoration. Each dormitory receives at most one manager per recovery kind; an operator with both skills occupies one slot. Unfinished primary recovery and specialized reservations retain [INV-SCHED-03] protection.

The existing two-pass bed opener tracks selected rooms per recovery kind instead of requiring a prior group-manager count. No separate priority model or task queue is introduced.

## Verification and review

Offline tests cover occupied ordinary replacement beds, an unavailable group manager, a Fiammetta dorm without a group manager, primary protection and one manager per kind. Standards review preserves shared planning and reservations; specification review checks that all eligible managers precede fillers.
