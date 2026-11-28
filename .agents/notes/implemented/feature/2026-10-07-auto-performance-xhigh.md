---
title: Automatic Performance Xhigh Baseline
status: implemented
category: feature
date: 2026-10-07
---

# Automatic Performance Xhigh Baseline

[中文](2026-10-07-auto-performance-xhigh.zh.md)

## Contract

[INV-SCHED-30] Automatic Selection Baseline: Automatic selection starts at `xhigh` on every platform, and repeated failures lower one level without exceeding the active cap or changing explicit modes and timing settings.

All platforms expose `xhigh`, `high`, `medium` and `low`, share numeric defaults and use the same feedback thresholds. Explicit selections survive configuration loading, saving and execution. Before four feedback samples, automatic selection uses `xhigh` subject to any failure cap. An `xhigh` observation average below 0.35 retains that mode; at or above 0.35 it selects `high`. A `high` average at or below 0.2 selects `xhigh`; otherwise the existing high, medium and low thresholds apply. Two selection failures without a completed selection lower one level. Three completed selections release the failure cap. Each selection workflow retains its fixed profile.

## Implementation Boundaries

The pre-flight complexity check retains the existing performance policy, failure-cap helper and configuration store. No additional policy abstraction or persisted field is introduced. Numeric defaults use the existing `xhigh` values on every platform; saved independent timing values remain unchanged. Configuration schemas and domain glossary definitions remain unchanged.

## Verification

Offline performance tests cover shared startup defaults, feedback hysteresis, all downgrade levels, warmup and measured-feedback caps, workflow snapshots, Android high-mode persistence and feedback upgrades, and preserved timing values. Frontend tests cover the shared baseline across platforms, backend verdicts and explicit modes.

Dormitory recovery entry tests verify that two preselection feedback failures lower `xhigh` to `high` on every platform, with an exact cap and effective-mode assertion for each platform.

Settings rendering, the callable FAQ and the shipped guide now state the same starting mode as runtime execution. The regression first rejects the stale Android medium guidance, then verifies the corrected notice for Android, macOS, Windows and Linux. No performance strategy or saved configuration changes are needed for this repair.

The platform-unification repair passes 332 focused backend cases across performance, legacy selection, Android-managed configuration, configuration persistence, dormitory recovery and game tests. It removes Android-specific startup and numeric defaults while preserving saved independent settings. The CI failure in Android configuration isolation is an outdated assertion that forces an imported extreme selection to medium; the repaired regression covers every mode while retaining Android-owned device settings. Five focused frontend suites pass 79 cases, including shared defaults, save/reload and explicit adoption.
