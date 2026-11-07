---
title: Workshop Threshold Fallback
status: implemented
category: feature
date: 2026-10-07
---

# Workshop Threshold Fallback

[English](2026-10-07-workshop-threshold-fallback.md) | [中文](2026-10-07-workshop-threshold-fallback.zh.md)

## Contract

**[INV-UI-11] Workshop Threshold Fallback**: One-click workshop setup synchronizes BOX once, lowers only empty categories by five percentage points down to zero, keeps each category at its first nonempty selection, and applies all lists only after successful reads without changing the configured threshold.

Opening the settings reads recommendations at the configured threshold without lowering it. Non-T5, T5 and skill-summary lists resolve independently. Categories still empty at zero remain empty; failed synchronization or recommendation reads preserve all configured lists.

## Implementation

Pre-flight review finds two recommendation-loading callers: settings reads and one-click synchronization. Each empty category runs a bounded loop through `loadWorkshopOperators` inside `syncWorkshopOperators`. Requests retain the starting `min_bonus` and lower only the target category through `fodder_min_bonus`, `t5_min_bonus` or `book_min_bonus`. The existing endpoint validates these optional integer thresholds with the same 0–1000 boundary. It adds no endpoint, persistent configuration field or scheduling change. Existing ownership, unlocked-skill and Scheduling Plan filters remain authoritative. The backend selection uses each category’s override while retaining the original threshold for other categories. This prevents a lower material threshold from assigning a skill-summary candidate elsewhere before the target category is evaluated. No redundant abstraction is removed and no glossary change is required.

The settings dialog applies the completed lists and describes the category-specific fallback. Runtime allocation already retains each recipe’s highest-bonus selected operators below the configured threshold, so fallback operators remain usable without a new configuration field. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the permanent invariant.

## Verification

[Focused frontend tests](../../../../ui/src/utils/workshopOperators.test.js) cover an immediate match, 80-to-75 fallback, repeated empty thresholds, independent category thresholds and preservation of populated lists, zero termination, one BOX synchronization, failed fallback reads and unchanged ordinary reads.

[Backend regressions](../../../../arknights_mower/tests/workshop_recommendation_tests.py) use real unlocked skills for 75, 70 and 60 percent skill-summary candidates, preserve both material lists, reject invalid category thresholds and verify generated skill-summary recipes under the unchanged 80 percent configuration.

The focused frontend suite passes 34 tests; the focused recommendation, allocation, curated-reference and roster suites pass 60 tests.

## Standards Findings

PASS: The loop is bounded by the existing nonnegative threshold and preserves the existing request-validation boundary.

## Spec Findings

PASS: Each category keeps its first nonempty list independently; lowering an empty skill-summary list neither adds lower-bonus operators to materials nor changes the displayed starting threshold.
