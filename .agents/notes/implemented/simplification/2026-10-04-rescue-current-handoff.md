---
title: Current rescue handoff coverage
status: implemented
category: simplification
date: 2026-10-04
---

# Current rescue handoff coverage

## Contract and simplification

[INV-SCHED-09] admits rescue handoff when measured-ready primaries can return and unfinished groups have complete normal replacements and beds. [INV-SCHED-03] preserves actual staffing verification, personal mood caps, protected releases and specialized compensation. Unknown or predicted operator mood cannot establish handoff readiness. Bed capacity comes from the effective normal plan, excluding manager slots temporarily opened by rescue. Normal standby operators use personal rescue thresholds as recovery targets; full-recovery requirements retain personal mood caps. Already returned workers retain ordinary shift-off checks instead of needing to recover again after working during a partial handoff.

The readiness, deployment and final observation paths share `_emergency_handoff_feasible`. They verify current coverage without a second call to `native_opportunity` for every returning group. Future shared replacement contention, unknown recovery times and unknown depletion rates do not block current handoff. The entry projection and historical target calculations retain their existing callers and rules. The obsolete `check_rotation` option is removed.

## Verification and review

Offline tests exercise two groups sharing one future replacement, an unfinished resident with and without a recovery timer, zero observed depletion rates, unknown and predicted primary mood, exhausted replacements, insufficient beds and full-rest targets. Standards review preserves isolated projections and existing task boundaries. Specification review confirms current coverage and actual readback remain mandatory without requiring all groups to finish recovering.
