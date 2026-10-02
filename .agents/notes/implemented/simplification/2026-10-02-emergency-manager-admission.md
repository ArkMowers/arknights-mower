---
title: Intelligent Rescue Manager Admission
status: implemented
category: simplification
date: 2026-10-02
---

# Intelligent Rescue Manager Admission

## Contract

[INV-SCHED-07] allows measured-completed dormitory managers to yield intelligent-rescue beds regardless of their configured recovery priority. Unfinished or predicted completion does not authorize this admission. Other residents retain shared recovery tiers, exclusions and task reservations. Ordinary dormitory scheduling retains its existing policy.

## Simplification

The existing Operators._slot_takable predicate handles planning and actual selection. Its configured-resident completion condition accepts manager identities from the frozen dormitory layout without a priority exception. No setting, state field, helper or compatibility path is added. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the interface guarantees.

## Verification

Offline tests retain the real emergency bed planner and dormitory selection. Both manager positions cover default and explicit priority, measured completion, unfinished recovery and prediction. Separate residents retain higher-priority protection and a lower-tier unfinished resident follows shared takeover rules. Device recording is isolated.

Eight focused offline suites pass 535 tests. Scoped Ruff, formatting and whitespace checks pass.

## Review

Standards Findings: one shared predicate keeps plan and selection admission consistent.

Spec Findings: configured manager priority cannot block a measured-completed manager from yielding a recovery bed.
