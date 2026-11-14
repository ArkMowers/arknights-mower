---
title: Medicine Expiry Threshold
status: implemented
category: simplification
date: 2026-10-11
---

# Medicine Expiry Threshold

## Contract

[INV-MAA-09] makes `medicine_expire_days` independent of weekday. MAA Fight receives the configured threshold. Local operation retains its existing expiring-potion recognition when the threshold is positive. Zero disables expiring-potion use. Both spellings of the retired weekend-only setting are ignored on configuration reads and submissions, and disappear on save without changing the threshold or weekly plans.

## Simplification

The weekend setting has two execution consumers, in `BaseSchedulerSolver.append_maa_task` and `OperationSolver.transition`, plus the weekly-plan checkbox and configuration store. Removing the field, its spelling migration, the checkbox and both weekday gates leaves the existing remaining-day setting as the sole control. Native recognition remains unchanged and does not gain MAA's precise remaining-day comparison.

## Verification

Focused regressions cover all seven MAA weekdays, zero disabling, old configuration reads and submissions, save/reload, frontend rendering and threshold autosave, and native potion acceptance and rejection. Device operations and network calls remain mocked.

## Standards Findings

PASS. [INV-MAA-09] is registered in coding standards, the subsystem contract and the review checklist. Both glossary entries have explicit user approval. The removal adds no device actions, network requests, runtime state or resource owners. Ruff, ESLint, formatting and governance checks pass.

## Spec Findings

PASS. The checkbox, persisted field, spelling migration and both execution gates are removed. Old keys are ignored without changing the configured threshold, and nonpositive values retain disabled behavior. Backend and governance regressions pass with 149 tests; frontend regressions pass with 24 tests on alpha `6e017e4eb678b249fc95be03feecf88012a23ff9`. Structural checks retain two existing archived test-reference warnings. User-reported Sunday non-use is not reproduced against a live MAA instance; this change removes the restriction independently of its weekday calculation.
