---
title: Scheduler CI Fixtures
status: implemented
category: testing
date: 2026-10-04
---

# Scheduler CI Fixtures

## Contract

[INV-SCHED-09] requires completed rescue staffing before exit and admits unfinished recovery primaries before spare-bed replacements. [INV-SCHED-03] validates the actual resident and bed before release. [INV-SCHED-20] keeps cross-dormitory recovery allocation inside the shared scheduling projection.

## Test Boundaries

Personal-limit recovery fixtures explicitly complete staffing. Predicted-mood exit fixtures exhaust normal replacements so an unfinished measured primary cannot leave through a feasible early handoff. Separate false and absent staffing states verify that completed mood alone cannot authorize exit.

Rescue bed tests cover both configured replacement priority tiers before and after measured primary recovery. Training readback fixtures provide the operator name required by the ordinary mood scan. Workshop release dispatch uses validated `Operators` and a real five-slot dormitory with its resident in the Free bed; only device arrangement and unrelated dispatch operations are mocked. Dispatch verifies the exact release arrangement, clears the completed task, and does not invoke crafting or exception reporting.

## Verification

Twelve focused offline modules pass with 692 tests and 32 subtests. One existing Pydantic fixture serialization warning remains. The tests cover personal limits, rescue priority, training restart, workshop dispatch, single-Free departures, admission, recovery, release, shift convergence, automatic rescue and governance. No production scheduling behavior changes in the CI repair.

## Standards Findings

Pass: fixture corrections reuse existing models and invariants without adding production fallback branches, configuration or scheduling abstractions. No glossary changes are required for these test boundaries.

## Spec Findings

Pass: rescue admission and measured exit match the existing contract, and workshop dispatch exercises the release projection required by the [single-Free departure decision](../bug-fix/2026-10-04-single-free-departure-priority.md).
