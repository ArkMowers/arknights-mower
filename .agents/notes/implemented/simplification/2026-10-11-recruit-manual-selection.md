---
title: Recruitment Manual Selection
status: implemented
category: simplification
date: 2026-10-11
---

# Recruitment Manual Selection

[English](2026-10-11-recruit-manual-selection.md) | [中文](2026-10-11-recruit-manual-selection.zh.md)

## Contract

**[INV-RECRUIT-01] Manual Selection Authority**: Manual five-star recruitment never queues automatic selection unless the unique-choice exception is enabled and exactly one calculated choice remains. The [subsystem contract](../../../../docs/subsystems/recruitment.md) owns the selection rules.

## Evidence and simplification

`RecruitSolver.transition` is the sole production caller of `recruit_tags`. The screenshot selects manual mode and disables the unique-choice exception. The existing nested predicate only exits when the exception is enabled and multiple choices remain, so disabling the exception permits automatic selection. The corrected predicate exits when the exception is disabled or multiple choices remain. It reuses the existing notification, slot advance and return path without adding a helper, configuration field or policy abstraction. The condition remains in its existing branch; formatting wraps the corrected expression across lines. Equivalent-result collapsing remains unchanged. No glossary definitions, configuration schema, device lifecycle or base scheduling mechanics change.

## Verification

[Policy regressions](../../../../arknights_mower/tests/recruit_policy_tests.py) assert queued selection or slot advance for both modes and exception states, single and multiple choices, equivalent results and other rarities. Notification delivery and device control use offline substitutes.

Before correction, three regressions fail because disabling the exception queues selection in manual mode. After correction, the focused recruitment and governance suites pass 37 tests. Ruff lint, formatting and repository governance checks pass.

After moving the isolated repair onto alpha commit `a10a99d7`, the same focused suites pass 50 tests. Structural governance checks pass with two existing archived test-reference warnings; modified-file Ruff lint, formatting and diff whitespace checks pass.

## Standards Findings

PASS: The change preserves configuration and device boundaries, registers the invariant in the subsystem contract, coding standards and review checklist, and adds no glossary wording or external operations.

## Spec Findings

PASS: Manual mode with the exception disabled leaves five-star selection unqueued for both single and multiple choices. Enabled unique-choice handling, automatic mode, equivalent-result collapsing and other rarities retain their existing behavior.
