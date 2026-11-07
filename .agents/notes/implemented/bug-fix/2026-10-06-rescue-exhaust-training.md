---
title: Exhaustion admission and training deployment
status: implemented
category: bug-fix
date: 2026-10-06
---

# Exhaustion admission and training deployment

## Contract and simplification

[INV-SCHED-09] excludes exhaustion workers and their groups from current rescue contention until they rest, reach a personal mood floor or have a due exhaustion shift-off task. Initial admission and current native projections share this predicate. Training deployment preserves existing slot protections and task reservations; its selection page does not supply mood evidence.

The fix moves the existing training-page bypass before rescue card observation and adds the destination room to staffing validation. It introduces no scheduling state or configuration. Existing exhaustion support still coordinates an occupied replacement before retrying complete group replacement; no advance reservation is added.

## Verification and review

Offline regressions cover the observed pre-exhaustion false admission, due and future tasks, grouped members, custom floors, training cards without mood, training protection and occupied-replacement coordination. Standards review checks isolated current projections and shared staffing guards. Specification review retains ordinary unknown-mood rejection outside training and existing recovery completion requirements.

Current native projections also apply feasible exhaustion-support arrangements in an isolated branch and verify that the group can then rest. A workable coordination result prevents rescue admission; blocked coordination does not count as successful recovery.
