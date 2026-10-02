---
title: Intelligent Rescue Target Evaluation Isolation
status: proposed
category: bug-fix
date: 2026-10-03
---

# Intelligent Rescue Target Evaluation Isolation

## Contract

[INV-SCHED-09] reuses the read-only expression evaluation model during recovery-target and native recovery-opportunity projection. Mutable operators, dormitory beds, plans and configuration remain isolated from runtime state. Evaluation-injected builtins and extension handles never require serialization.

## Simplification

Target calculation uses the existing deepcopy memo convention from complete shift simulation. The backend directives require the same projection ownership boundary. No new helper, cache, state field or compatibility path is added. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the invariant.

## Verification

The offline regression injects an actual PyCapsule into the evaluation model, evaluates an expression, and runs real target calculation with a native-opportunity probe. It verifies evaluator identity, mutable state isolation and history target calculation. The same test fails before the fix with the PyCapsule copy error. Immediate rotation, blocked rotation and pending-task opportunity searches run with the same actual PyCapsule and verify runtime state remains unchanged. Existing real backup handoff regressions remain enabled. Seven focused suites pass 298 tests and 4 subtests.

## Review

Standards Findings: pending independent review.

Spec Findings: pending independent review.
