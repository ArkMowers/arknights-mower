---
title: Configurable Group Recovery Spread
status: implemented
category: simplification
date: 2026-10-06
---

# Configurable Group Recovery Spread

## Contract

[INV-SCHED-21] defines order-independent group recovery spread. Group recovery spread is the difference between the latest and earliest predicted recovery completion times among members participating in ordinary return timing. Its delayed-return threshold is configurable in advanced plan settings and defaults to 60 minutes; the existing extra-wait limit remains enforced.

## Implementation

The single group-return calculation replaces power-plant constants with one validated minute setting (1–1440). The existing advanced-plan whitelist, configuration store and extra-wait cap carry the setting without a separate policy layer. Explicit full-recovery requirements and participant selection retain their existing rules.

## Verification

Focused tests cover bed ordering, two and three power plants, the strict threshold boundary, extra-wait limits, configuration persistence and plan import/export.

## Standards Findings

Shared calculation and existing configuration paths; no new task type or device operations.

## Spec Findings

The default is 60 minutes for all power-plant layouts. Users configure the threshold beside the existing delayed-return controls.
