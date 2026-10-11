---
title: Retained Dormitory Selection Prefix
status: implemented
category: simplification
date: 2026-10-12
---

# Retained Dormitory Selection Prefix

## Contract

[INV-SCHED-02] preserves every verified full-mood fixed occupant and Fiammetta in the temporary recovery roster, regardless of preceding position. Low or unknown mood in other preceding fixed positions requires temporary padding. Single-target recovery providers remain present. Differential selection preserves the complete unchanged prefix from verified room occupancy and rebuilds only the changed suffix. Card display order supplies click coordinates, not selection-number evidence. Unexpected occupants and full-selection retries retain complete rebuilding; actual room readback verifies final positions.

## Caller Evidence

`choose_agent` receives `preserve_dorm_occupants=True` from recovery setup and roster restoration. Both callers share `BaseMixin.reorder_selected_agents`, including its production timing and observed card coordinates. One matching-prefix calculation replaces special handling for the first occupant and preserves all unchanged preceding positions. The [full-mood retention decision](2026-10-12-full-mood-recovery-retention.md) governs the recovery roster.

## Verification

Offline `choose_agent_filter_tests.py` records every selection transition across performance modes and differing card display orders. `dorm_recovery_tests.py` runs real selection within recovery setup and restoration, and checks full, low and unknown mood at multiple fixed positions. Recovery, grouped replacement and selection verification suites preserve final placement and failure handling.

## Standards Findings

PASS: Selected-card verification locates every card before input; actual room occupancy supplies the retained prefix. Explicit suffix rebuilding preserves placement without interpreting card display order as selection numbers. Full-selection recovery remains available.

## Spec Findings

PASS: Every unchanged preceding occupant remains selected during ordinary setup and restoration. Full-mood fixed occupants and Fiammetta remain at their configured positions in temporary rosters, including when another fixed position requires padding. Unexpected occupants trigger full selection. Focused selection, recovery, grouped replacement and governance tests verify the contract.
