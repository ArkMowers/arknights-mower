---
title: Automatic Performance Xhigh Baseline
status: implemented
category: feature
date: 2026-10-07
---

# Automatic Performance Xhigh Baseline

[中文](2026-10-07-auto-performance-xhigh.zh.md)

## Contract

[INV-SCHED-30] Automatic Selection Baseline: Desktop automatic selection starts at `xhigh`, Android starts at `medium`, and repeated failures lower one level without exceeding the active cap or changing explicit modes and timing settings.

Desktop automatic selection uses `xhigh`, `high`, `medium` and `low`. Before four feedback samples, it uses the platform baseline subject to any failure cap. An `xhigh` observation average below 0.35 retains that mode; at or above 0.35 it selects `high`. A `high` average at or below 0.2 selects `xhigh`; otherwise the existing high, medium and low thresholds apply. Two selection failures without a completed selection lower one level. Three completed selections release the failure cap. Each selection workflow retains its fixed profile.

## Implementation Boundaries

The pre-flight complexity check retains the existing performance policy, failure-cap helper and configuration store. No additional policy abstraction or persisted field is introduced. Numeric defaults for `xhigh` equal the existing desktop defaults. Configuration schemas and domain glossary definitions remain unchanged.

## Verification

Offline performance tests cover desktop startup, feedback hysteresis, all downgrade levels, warmup and measured-feedback caps, workflow snapshots, Android restrictions and preserved timing values. Frontend tests cover the visible desktop and Android baselines, backend verdicts and explicit modes.
