---
title: Cross-Dormitory Priority Regressions
status: implemented
category: testing
date: 2026-10-06
---

# Cross-Dormitory Priority Regressions

## Contract

[INV-SCHED-20] separates bed admission from single-target ownership. Existing eligible residents compete when admission triggers allocation; a newly admitted standby or replacement need not occupy the original vacancy after allocation.

## Simplification and Verification

Four historical assertions require fixed admission positions. Their replacements verify projected occupant sets, the priority of the resulting single-target resident and stable replanning. The three-room case verifies that all three admitted residents obtain their corresponding single-target slots. No production logic, fixture identity, configuration or glossary changes are needed.

## Standards Findings

Pass: tests use existing projections, preserve live-state checks and remain offline. The four affected suites pass 355 tests and 6 subtests; Ruff passes.

## Spec Findings

Pass: the tests enforce the approved cross-dormitory allocation instead of restoring the earlier fixed-resident behavior. Bed ownership remains complete and takeover removes only its intended resident.
