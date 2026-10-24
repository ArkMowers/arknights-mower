---
title: Intelligent Rescue Specialized Boundaries
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Specialized Boundaries

## Contract

[INV-SCHED-03] keeps personal mood-limit release deadlines active during intelligent rescue. Frozen metadata planning rebuilds only strict releases from actual bed identity and the existing recovery deadline; ordinary working shifts remain paused. Every rescue tick updates these deadlines, after room readback when observation is due and before planning bed reservations. Pending releases reserve both original beds and occupants. Completed personal-limit recovery cannot re-enter emergency beds; actual mood still determines rescue-target completion.

[INV-SCHED-04] restores observed temporary staffing after trade order runs and Fiammetta swaps, including explicit vacant slots. During intelligent rescue, specialized arrangement retains empty strings for the existing selection path to clear. Explicit `Free` remains a vacancy-fill request; ordinary arrangements retain their existing empty-slot behavior.

## Simplification

The existing personal-limit planner and empty-slot selection path supply both behaviors. The fix adds no configuration, task marker, recovery pipeline or compatibility alias. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the scheduling guarantees.

## Verification

Offline tests use real metadata planning, rescue ticks, bed-identity validation, room arrangement and selection. They cover deadlines before mood checks, repeated planning, partial recovery, changed occupants, new measured completion, pending-release bed identity, completed-limit readmission, immediate and queued compensation, Fiammetta restoration without snapshot metadata, and unchanged explicit `Free` filling. Device and storage boundaries use test doubles.

## Review

Standards Findings: personal limits retain their existing identity and deadline rules while ordinary shifts remain frozen. Compensation uses existing specialized task types and vacancy selection.

Spec Findings: personal limits remain actionable before another mood check; specialized restoration preserves observed vacant slots without disabling requested vacancy filling.

Eight focused offline suites pass 234 tests and 4 subtests. Scoped Ruff, formatting and whitespace checks pass. No live-device integration runs are performed.
