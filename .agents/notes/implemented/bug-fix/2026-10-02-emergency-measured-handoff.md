---
title: Intelligent Rescue Measured Handoff
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Measured Handoff

## Contract

[INV-SCHED-03] retains frozen dormitory operator identities when emergency beds open. Personal limits remain applicable to original fixed residents, including completed recovery cycles. Normal plan replacement clears these temporary identities; rescue restart rebuilds them from the persisted dormitory layout. Manager restoration excludes completed personal-limit cycles.

[INV-SCHED-09] distinguishes predicted mood from actual readings. Dormitory deadline correction, ordinary release completion and crafting arithmetic mark mood as predicted; actual room readings clear that mark. Shadow reconstruction and cache restoration retain the source. Intelligent rescue target checks reject predicted readings. Strict release reads departing mood before selection even when idle recovery is disabled. Predicted idle targets lose their unverified timestamp and release marker before bed planning, so actual readings remain attainable; actual completed cycles retain their markers.

A returning episode retains the specialized-compensation and temporary-staffing gates. Pending primaries still require actual recovery targets. Primaries already observed at their configured working positions require actual readings and complete native feasibility instead of their initial recovery targets. Lost feasibility clears the pending handoff and resumes bed recovery. Targets remain unchanged by handoff retries.

## Simplification

The fix reuses persisted dormitory layout, existing actual departure reads and the native feasibility planner. It adds one mood-source flag and transient configured names, with no setting, compatibility path or second staffing scheduler. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the interface guarantees.

## Verification

Offline regressions exercise real room reads, deadline correction, shadow reconstruction, rescue ticks, partial arrangements, native feasibility and bed planning. They cover personal limits for fixed residents, repeated bed opening, normal plan replacement, predicted versus actual target completion, delayed or failed partial handoff, returning restart, specialized compensation and recovery after feasibility loss. Physical device and storage boundaries use test doubles.

## Review

Standards Findings: actual source survives reconstruction, personal-limit identity survives temporary bed opening, and failed handoff returns to a schedulable recovery phase.

Spec Findings: pending target checks remain measured; already returned workers retain native feasibility checks; ordinary staffing stays frozen until handoff completes.

Thirteen focused offline suites pass 371 tests and 4 subtests. The ten partial-handoff regressions fail against the previous methods and pass against the current implementation. Scoped Ruff, formatting, whitespace and all governance gates pass. No live-device integration runs are performed.
