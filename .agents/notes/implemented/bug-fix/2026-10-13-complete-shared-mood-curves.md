---
format: decision
title: Complete Shared Mood Curves
status: implemented
category: bug-fix
date: 2026-10-13
---

# Complete Shared Mood Curves

## Problem

Mood samples record the active group at observation time. Default reports partitioned a shared operator's history by those recorded groups and placed former ungrouped observations in a separate personal card. This split prevented any bound group from showing the operator's complete mood curve.

## Decision

The [Complete Shared Mood Curves rule](../../../../docs/subsystems/base-scheduler.md#complete-shared-mood-curves) owns report membership. The report projects each configured multiple-group operator's complete seven-day history into every declared binding in saved main and backup plans. Repeated declarations add no duplicate samples. Shared dormitory residents join named-operator query selection; ordinary operators retain existing filters and membership.

## Alternatives considered

An independent personal card combines the history but removes the shared operator from the group comparisons requested by users. Partitioning by the recorded active group preserves the original observation label but leaves each group with an incomplete curve. Report projection preserves the original database evidence while supplying complete group comparisons.

## Consequences

The report preserves event annotations and sorts samples chronologically across former groups. It changes neither recorded observations nor scheduling state and requires no database migration. An operator with several declared bindings repeats its curve in several report cards; saved declarations keep those memberships stable across active backup changes.

## Verification

[Focused SQLite tests](../../../../arknights_mower/tests/multi_group_mood_report_tests.py) cover complete three-binding history, former ungrouped samples, time ordering, seven-day filtering, annotations, backup-only bindings, repeated declarations, shared dormitory residents, single bindings, favorites, Fiammetta and configuration immutability. A read-only probe against the remote fui data produces identical 37-point curves for Yuki Makoto in all three declared groups; it changes no remote file or running service.
