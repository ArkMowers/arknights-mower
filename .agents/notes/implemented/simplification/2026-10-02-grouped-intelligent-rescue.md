---
title: Grouped Intelligent Rescue
status: implemented
category: simplification
date: 2026-10-02
---

# Grouped Intelligent Rescue

## Contract

[INV-SCHED-09] preserves the frozen primary schedule during intelligent rescue. One complete bound group receives complete automatic skill-based replacements and dormitory positions before leaving work. Each group returns to its original primary positions after all required members meet measured targets and continuing rotation is feasible. Other groups remain unchanged. Backup transitions remain frozen until final exit.

## Simplification

Group staffing replaces the initial whole-facility takeover and repeated facility repair scans. It reuses selection-card eligibility, facility scoring, complete replacement matching and the shared dormitory planner. The planner's explicit member scope omits ordinary filling while allocating a shift-off group. No published-state migration or additional configuration is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the scheduling guarantees.

## Persistent Responsibility

Staffing and early return save their complete plans and member reservations before device arrangement. Actual occupancy determines completed positions after partial execution and restart. Early return owns an explicitly authorized rescue task context and restores the prior task on every outcome. Targets remain measured; card estimates only screen temporary working replacements and do not block low-mood primary dormitory admission or measured primary returns. Completed group returns invalidate obsolete dormitory filling for those members. Ordinary spare-bed filling follows shared recovery priority. Intelligent rescue preserves the normal dormitory layout and has no separate manager clearance, manager restoration or all-position opening path. After a group returns, every temporary working position is rescored with the fixed primary operators’ skills; actual mood readings remain unchanged.

Selection rejection retains unfinished group obligations and triggers a fresh automatic match, including unfinished original-primary slots. A shortage cannot requeue rejected names. The existing mood-check task carries full departure and return membership before specialized planning; shared dormitory and workshop reservations release those members only after measured completion.

## Verification

Offline group-bed, staffing and return regressions cover complete admission, rollback, automatic replacement shortages, measured completion, native rotation blocking, backup freeze, release windows and partial return restart. Targeted existing rescue and compensation suites retain production feasibility and observation checks.

## Review

Standards Findings: PASS. Independent review of the unchanged production snapshot confirmed the selection boundary, fresh matching and complete reservations. The final test-only review of `8a489841` confirmed ordinary dormitory fixtures and effective assertions; governance, scoped Ruff and formatting passed. Glossary supplementation remains subject to explicit wording approval.

Spec Findings: PASS. The final independent review ran 142 targeted tests, 14 governance tests, 13 production diagnostics and 10 boundary or negative-control diagnostics. Earlier selection, retry and reservation findings are resolved. Four retired bed-opening tests now exercise ordinary dormitory allocation without restoring the removed interface. All verification remained offline.
