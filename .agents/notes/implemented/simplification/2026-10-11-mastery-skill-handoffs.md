---
title: Mastery Skill Handoffs
status: implemented
category: simplification
date: 2026-10-11
---

# Mastery Skill Handoffs

## Contract

[INV-SCHED-47] keeps eligible same-operator skills adjacent, orders unstarted skills by ascending current mastery, and admits training only when the group’s summed remaining costs are craftable from shared stock and permitted recipes; only the current skill’s materials are prepared. A final stage reserves a reducer when the next skill belongs to the same operator and already has mastery one. Observed assistant identity and more than five hours of recorded training authorize inherited halving across skill boundaries.

The existing [scheduler contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants) also owns the warning for any selected Amiya mastery skill and the per-visit form check. Explicit form IDs preserve the selected skills despite their shared name. A missing form preserves a reliably observed reducer, skips the current visit's mutations and rechecks on later visits; confirming the target skill resumes execution. This does not add automatic form switching or a permanent training-room pause. The identity check reuses [INV-REC-05].

A same-operator seven-to-one successor excludes reducers from continuing mastery-three assistance, even when they provide the highest bonus. The start path consumes confirmed inherited halving before replacing the assistant; recovery and queued handoffs reuse the same route restriction. Queue edits reevaluate the restriction and restore ordinary reducer protection when it no longer applies.

## Simplification Evidence

`stage_route` and `schedule_support_swap` share the five-hour reducer allowance and a ten-minute default buffer. The three legacy buffer keys remain readable with ten-minute defaults; explicit settings remain user choices. Control Center staffing confirmation refreshes the observed countdown and pending handoff. The reducer allowance includes the configured full Control Center bonus, while current progress uses actual staffing.

## Verification

Focused offline tests cover adjacent order, per-skill material admission, final-stage reducer admission, cross-skill recorded work, default margins and staffing-driven deadline replacement. Existing training protection and observed skill attribution remain enforced.

Focused frontend page tests cover any Amiya form selection, multiple forms, filtering, removal, saved-plan reload and individual/bulk submission IDs. The Amiya form suite covers dispatch through a mismatched form and a later confirmed form, bounded unreadable-text retries, cancellation and device recovery propagation, repeated room inspection, mutation suppression with schedule following, and explicit all-profession selection. Real OCR reads offline rendered skill names for all three forms; game-screen verification remains outstanding. The handoff suite covers non-reducer selection and replacement during mastery three when the next skill starts at basic level, inherited halving and queue edits. Existing API and task-contract evidence covers distinct same-name form resolution and rejection of invalid explicit IDs without name fallback.
