---
title: Mastery Skill Handoffs
status: implemented
category: simplification
date: 2026-10-11
---

# Mastery Skill Handoffs

## Contract

[INV-SCHED-47] keeps eligible same-operator skills adjacent, orders unstarted skills by ascending current mastery, and admits training only when the group’s summed remaining costs are craftable from shared stock and permitted recipes; only the current skill’s materials are prepared. A final stage reserves a reducer when the next skill belongs to the same operator and already has mastery one. Observed assistant identity and more than five hours of recorded training authorize inherited halving across skill boundaries.

The existing [scheduler contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants) also owns the multi-form selection warning. Explicit form IDs preserve the selected Amiya skills despite their shared name; this does not add automatic form switching.

## Simplification Evidence

`stage_route` and `schedule_support_swap` share the five-hour reducer allowance and a ten-minute default buffer. The three legacy buffer keys remain readable with ten-minute defaults; explicit settings remain user choices. Control Center staffing confirmation refreshes the observed countdown and pending handoff. The reducer allowance includes the configured full Control Center bonus, while current progress uses actual staffing.

## Verification

Focused offline tests cover adjacent order, per-skill material admission, final-stage reducer admission, cross-skill recorded work, default margins and staffing-driven deadline replacement. Existing training protection and observed skill attribution remain enforced.

The warning follow-up passes four frontend page tests covering same-form selection, multiple forms, filtering, removal, saved-plan reload and individual/bulk submission IDs. API and task-contract tests pass 67 cases, including distinct same-name form resolution and rejection of invalid explicit IDs without name fallback.
