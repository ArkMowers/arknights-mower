---
title: Initial Fiammetta and Release Stability
status: implemented
category: bug-fix
date: 2026-10-04
---

# Initial Fiammetta and Release Stability

## Contract

[INV-SCHED-03] reuses a personal-limit release when its occupant, bed, limit and recovery deadline are unchanged. Actual deadline or bed changes replace that task. [INV-SCHED-04] prioritizes initialized full-mood Fiammetta charging and restoration before ordinary work and rescue evaluation, while retaining due critical-task protection.

## Simplification

Existing release tasks hold their planning source and reserved start. The planner reuses these tasks instead of adding a global log cache. Actual advances remain INFO messages. Fiammetta uses the existing target selection, charge and restoration sequence with one startup priority marker; unknown mood, missing targets and candidate-retry cooldown do not force charging.

## Verification

Offline tests cover task identity across replanning, changed deadlines and beds, absent and cached Fiammetta wakeups, measured eligibility, restoration priority, normal and rescue dispatch, and protected critical tasks.

The mood-limit deadline suite uses the shared `offline_maintenance` fixture, so live announcements and cached maintenance windows cannot alter its trade order timing. Injected active maintenance reproduces three timing failures without isolation; all six priority-window cases pass with isolation.

Targeted offline verification passes 372 tests and 4 subtests. Ruff and repository governance gates pass.

## Standards Findings

No device integration runs or new external resources. Mutable task ownership remains within the scheduler. Glossary text has explicit approval.

## Spec Findings

Initialization charging precedes rescue evaluation. Replanning retains unchanged release operation windows instead of repeatedly announcing identical advances.
