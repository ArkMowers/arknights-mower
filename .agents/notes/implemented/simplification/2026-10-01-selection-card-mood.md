---
title: Selection Card Mood Estimates
status: implemented
category: simplification
date: 2026-10-01
---

# Selection Card Mood Estimates

## Contract

Dormitory candidate selection reads each recognized card's face color in the existing selection frame: green maps to 24 and red maps to 0. Yellow cards use approximate white-bar length strictly between 0 and 24. Approximate readings support candidate ordering, full-card screening, and primary shift selection. Room inspection owns measured mood, sample timestamps, depletion rates, recovery deadlines, and mandatory personal limits.

## Simplification Audit

`scan_agent` serves ordinary and low-frame-rate selection; both paths reuse one pure estimator and one observation helper. `dorm_candidates` remains the shared planning and selection entry point. The card observation replaces repeated trial admissions for visibly full candidates and introduces no per-operator UI action or duplicate page scanner. Failed estimates remain unknown. Full residents are retained only after lower-mood eligible candidates are considered; empty beds still accept full padding.

## Guarantees

[INV-SCHED-15] Selection Estimate Isolation: Selection-card mood estimates support candidate screening, ordering, and primary shift selection only; they never overwrite measured mood, timestamps, depletion rates, recovery deadlines, or mandatory personal limits. Facility-completion events refresh only affected candidates and preserve unrelated estimates and search checks.

Card estimates expire after one hour. Actual mood readback and position changes invalidate only the affected estimate; cached occupancy reads preserve it. Facility-completion events refresh only affected candidates. An hourly exhausted-search reset clears all estimates. Actual valid mood takes precedence. Exclusions and task reservations remain authoritative.

[English](2026-10-01-selection-card-mood.md) | [中文](2026-10-01-selection-card-mood.zh.md)

## Verification

MuMu selection-card samples map clear red faces to exactly 0 and clear green faces to exactly 24, including selected green cards. Yellow 1/24 samples estimate approximately 1.3–1.5. Yellow-card bar estimates never reach the endpoint values, so near-full yellow cards remain recovery candidates. A selected red face with washed-out color remains unknown. Selected and unselected card strips are offline fixtures; estimation adds no capture or name-recognition operation.

Targeted regressions cover unreadable and partial bars, both selection modes without additional captures, estimate expiry and invalidation, actual-read precedence, full-resident retention, vacant-bed padding, unregistered candidates remaining `Free` through projection, stale actual mood versus current cards, and duplicate prevention when retaining multiple residents. Failed room-detail mood reads return unknown rather than verified full mood.

## Review

Standards Findings: Pass. [INV-SCHED-15] keeps estimates separate from measured values and timers; task reservations and mandatory limits retain precedence.

Spec Findings: Pass. Approximate selection supports low-mood admissions and full padding, retains eligible full residents only after ascending-mood screening, and preserves bounded search and normal unknown-read fallback.
