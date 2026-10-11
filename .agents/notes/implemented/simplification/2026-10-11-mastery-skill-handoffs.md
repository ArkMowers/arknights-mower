---
title: Mastery Skill Handoffs
status: implemented
category: simplification
date: 2026-10-11
---

# Mastery Skill Handoffs

## Contract

[INV-SCHED-47] keeps eligible same-operator skills adjacent, orders unstarted skills by ascending current mastery, and admits training only when the group’s summed remaining costs are craftable from shared stock and permitted recipes; only the current skill’s materials are prepared. A final stage reserves a reducer when the next skill belongs to the same operator and already has mastery one. Observed assistant identity and more than five hours of recorded training authorize inherited halving across skill boundaries.

## Simplification Evidence

`stage_route` and `schedule_support_swap` share the five-hour reducer allowance and a ten-minute default buffer. The three legacy buffer keys remain readable with ten-minute defaults; explicit settings remain user choices. Control Center staffing confirmation refreshes the observed countdown and pending handoff. The reducer allowance includes the configured full Control Center bonus, while current progress uses actual staffing.

## Verification

Focused offline tests cover adjacent order, per-skill material admission, final-stage reducer admission, cross-skill recorded work, default margins and staffing-driven deadline replacement. Existing training protection and observed skill attribution remain enforced.
