---
title: Aligned Fiammetta Mood History
status: implemented
category: bug-fix
date: 2026-10-08
---

# Aligned Fiammetta Mood History

## Contract

[INV-SCHED-35] records both participants of a complete charging observation at a shared before display time and a shared after display time one second later. Fiammetta's before point is 24, derived from the skill's full-mood requirement; her after point is measured. Target before and after values retain the existing reconstruction and observation rules. Incomplete observations and roster restoration produce no synthetic before points.

## Simplification

The existing exchange timestamp, participant readings and `save_agent_action` writer provide all required state. The change adds Fiammetta's missing before history point and aligns her after history time with the target. It introduces no extra screen read, persistent configuration, event type or scheduler state. Both Fiammetta points retain the charged operator annotation and the `fiammetta_charge` marker, excluding the exchange from ordinary rate calculations. Synthetic history never updates measured mood, depletion rate or recovery deadlines.

## Curve Spacing

The [Arknights Mower Base Scheduling Subsystem Description](../../../../docs/subsystems/base-scheduler.md#charging-curve-spacing) defines the ten-minute filtering window for ordinary Fiammetta curve points. Both curve readers reuse one SQL predicate and existing charging markers, preserving annotated exchange points and all raw observations. Filtering at query time also applies to previously recorded history without changing scheduling inputs, work/rest ratios or database schemas. Filtering precedes the selected curve's sample limit and includes relevant exchanges outside the displayed date range; histories without event columns retain their existing behavior.

## Verification

Offline regression covers zero, fractional and full target mood, both participant reading orders, stale Fiammetta mood cache, incomplete target observation and roster restoration. A temporary SQLite database exercises the real history writer and curve query, verifying four points, aligned timestamps and a one-second interval.

Temporary SQLite tests also cover ordinary points at the exchange, just before and exactly at ten minutes, repeated exchanges, both curve readers, preserved charged-operator annotations, unaffected target curves, unchanged database bytes, filtering before the sample limit, exchanges outside the displayed date range and legacy seven-column histories.

## Standards Findings

The change reuses existing bounded observation state and database lifecycle. Existing glossary terms suffice; scheduling mechanics and configuration schemas remain unchanged. The invariant is registered in coding standards, the subsystem contract and the review checklist.

## Spec Findings

Fiammetta's curve includes her full mood immediately before the exchange and her measured mood afterward, aligned with the charged operator's corresponding points.
