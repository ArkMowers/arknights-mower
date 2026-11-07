---
title: Shared Single-Free Recovery Allocation
status: implemented
category: simplification
date: 2026-10-04
---

# Shared Single-Free Recovery Allocation

## Contract

[INV-SCHED-20] uses the existing projected single-target allocation for a departure from a dormitory's only effective Free bed. All eligible residents participate in that event. Ordinary admissions retain their current allocation and mood changes alone preserve positions.

## Simplification

`prioritize_new_dorm_recovery` serves shift rearrangement and idle filling. Departure planning extends its candidate set rather than adding a separate sorter, persistent event flag or configuration option. Shift convergence and confirmed release reuse the same projection boundary.

## Verification

`dorm_single_free_departure_tests.py` checks cross-room ordering, stable replay, locks and confirmed departure paths without device or network I/O.
