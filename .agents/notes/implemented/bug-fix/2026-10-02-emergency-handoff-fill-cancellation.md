---
title: Intelligent Rescue Handoff Fill Cancellation
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Handoff Fill Cancellation

## Contract

[INV-SCHED-09] cancels episode-specific dormitory filling when handoff begins. Delayed, expired and restored filling tasks cannot reclaim primaries after their working staffing returns. Strict releases and specialized compensation remain in the queue. Returning startup applies the same filtering before task selection.

## Simplification

The existing emergency task filter rejects episode fills in the returning phase. Handoff calls that filter before arrangement and persistence. Recovery replans beds if handoff fails and the phase returns to recovering. No task identifier, state field, helper or compatibility path is added. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the guarantee.

## Verification

Offline regression retains the real bed planner, priority postponement, handoff feasibility, correction and arrangement entry. It covers delayed and expired fills, serialized task restoration and stale selected references at infra_main. The returning filter retains strict releases, specialized compensation and ordinary filling. Physical arrangement and storage boundaries are isolated.

Ten focused initialization, rescue, compensation and scheduling suites pass 638 tests and 26 subtests. Scoped Ruff, formatting and whitespace checks pass.

## Review

Standards Findings: queue filtering uses the existing task type flag and lifecycle phase.

Spec Findings: handoff cannot restore a primary to work and then replay obsolete episode filling into the dormitory.
