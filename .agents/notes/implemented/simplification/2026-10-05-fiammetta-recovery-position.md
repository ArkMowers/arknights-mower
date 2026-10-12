---
title: Preserve Fiammetta During Recovery Setup
status: implemented
category: simplification
date: 2026-10-05
---

# Preserve Fiammetta During Recovery Setup

## Contract

[INV-SCHED-02] preserves Fiammetta's position before the single-target recovery target regardless of her mood. Fiammetta never receives single-target recovery and does not participate in the padding mood check. Other preceding residents retain full-mood or eligible idle-padding requirements. The target keeps its final position through setup and restoration, and actual readback establishes the recovery record.

## Simplification

`recovery_order_plan` has one production caller, `BaseSchedulerSolver.ensure_dorm_recovery_order`. The existing retention condition excludes Fiammetta from unnecessary replacement; the caller excludes her from the existing competitor check. These two conditions remove redundant selection without introducing a helper, configuration option or persistent state.

## Verification

`dorm_recovery_tests.py` verifies Fiammetta in the first and third positions with zero, equal, higher and unknown mood; recovery succeeds without an available idle padding operator when her position is the only preceding non-manager position. Existing tests retain ordinary competitor checks, fixed target positions and readback requirements.

## Standards Findings

PASS. The change extends [INV-SCHED-02] in the subsystem contract, coding standards and review checklist. It adds no mutable state or resource lifecycle. Governance and targeted Ruff checks pass. Both glossaries append the separately approved Fiammetta residency rule.

## Spec Findings

PASS. Fiammetta stays in her original position during setup and roster restoration, and her mood does not block recording the real target. Recovery, Fiammetta-isolation and governance suites pass with 116 tests and four subtests on the current alpha base.
