---
title: Configured Rescue Schedule
status: implemented
category: simplification
date: 2026-10-04
---

# Configured Rescue Schedule

## Contract

The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) defines [INV-SCHED-09]. The rescue schedule owns ordinary working-facility assignments, separately from the frozen normal schedule. Entry evaluates rescue backups with the shared condition evaluator. Workers without replacements remain working. Overlapping normal primaries produce a startup warning and remain outside recovery targets.

All working facilities form one persisted dispatch. Actual occupancy determines outstanding rooms after partial failure or restart. Dormitory filling starts after confirmation of the full work roster. Specialized compensation and strict personal-limit releases retain their existing authority under [INV-SCHED-03].

Same-tier recovery candidates are ordered by group before spare-bed fillers. Handoff uses the normal complete replacement matcher and bed allocator for all unfinished groups together; measured-ready groups resume work only when native rotation remains feasible. Run-order selections and Fiammetta position and targets come exclusively from the rescue schedule.

## Implementation

The editor and condition controls share an injected plan store. Independent endpoints, autosave readiness and import routing preserve normal schedule data. Mower infrastructure settings contain the checkbox and rescue-editor entry, independently of normal schedule imports and exports. The editor retains the normal toolbar, facility interactions, group and replacement fields. Only the lower operator-rule sections remain hidden. The rescue toolbar returns to Mower settings. Its file-import button has a right dropdown that copies only the normal main roster. Export includes the entire rescue schedule. Effective facility types and staffing capacities must match the normal schedule before entry.

## Simplification

The existing plan schema, facility editor, condition evaluator, mood reader and task queue own this feature. No second normal scheduling engine is introduced. Per-facility pending progress and individual recovery targets have separate responsibilities.

## Verification

Targeted offline tests exercise backup overlays, roster completeness, overlap warnings, whole-roster dispatch, partial continuation, low-mood screening, continued work, recovery and compensation. Frontend tests check lazy-load autosave readiness and normal/rescue state isolation. No live-device integration tests run.

## Standards Findings

No outstanding findings. Shared plan parsing and condition evaluation preserve normal schedule state; partial tasks retain reservations and compensation. Governance and targeted static checks pass.

## Spec Findings

No outstanding findings. Targeted rescue suites pass 484 tests. Governance and route suites pass 17 tests and 4 subtests; six focused frontend suites pass 30 tests. Five changed Vue components compile successfully. Dormitory manager and Fiammetta position tests verify independent configuration, vacant slot identity and measured charging-room handoff. No real-device integration tests run.
