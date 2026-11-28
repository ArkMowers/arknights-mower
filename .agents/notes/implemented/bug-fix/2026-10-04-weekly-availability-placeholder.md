---
title: Weekly Availability Placeholder
status: implemented
category: bug-fix
date: 2026-10-04
---

# Weekly Availability Placeholder

## Contract

[INV-UI-04] binds unavailable cell placeholders and styling to the availability filter. Disabling the filter exposes all weekdays for selection and preserves existing `打` cells and saved plans. The [weekly editor contract](../../../../docs/subsystems/weekly-plan-editor.md) owns the interface guarantee.

## Simplification

Cell display and editing use the same filter-aware availability predicate in `MaaWeeklyTable`. The predicate replaces repeated conditions in individual and row-wide selection; no additional state or utility layer is required.

## Verification

Focused component rendering checks cover filtering enabled and disabled, placeholders, unavailable styling, selected cells and unchanged plan data. Existing weekly plan tests cover shared selections and priority ordering.

## Standards Findings

Pass: one shared predicate, no extra state, unchanged configuration schema and focused offline tests. The frontend suites pass 12 tests; governance verification passes 14 tests and four subtests.

## Spec Findings

Pass: disabling filtering removes `—` and unavailable styling, permits all weekdays and retains selected `打` cells. Enabling filtering retains unavailable placeholders and allows deselecting saved stages.
