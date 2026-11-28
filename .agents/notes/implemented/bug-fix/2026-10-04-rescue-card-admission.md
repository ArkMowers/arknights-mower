---
title: Card Mood for Rescue Admission
status: implemented
category: bug-fix
date: 2026-10-04
---

# Card Mood for Rescue Admission

## Contract

[INV-SCHED-09] permits valid card mood for initial contention and native-rotation feasibility when measured mood is unavailable. Existing measurements take precedence. Expired or absent card values remain unknown. Recovery completion and exit retain measured-mood requirements.

## Simplification

Admission reuses the shared candidate cache and existing native planner on an isolated arrangement projection. Estimate timestamps and values stay within that projection. Fiammetta charging feasibility retains measured mood. No device read or second candidate scan is added.

## Verification

Offline tests cover working and resting low groups, missing normal primaries with card estimates, available and exhausted normal covers, unknown or expired readings, real-reading isolation and rejection of estimated exit.

## Standards Findings

The existing projection boundary isolates mutable operators without copying extension handles. Domain wording has explicit user approval.

## Spec Findings

A completed card scan supplies the initialization decision even when normal primaries are idle after rescue staffing. Rate-based mood predictions do not become card observations.
