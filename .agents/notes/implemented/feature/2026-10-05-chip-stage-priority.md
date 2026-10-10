---
title: Chip Stage Priority
status: implemented
category: feature
date: 2026-10-05
---

# Chip Stage Priority

## Contract

[INV-UI-06] promotes all eight chip rows immediately below annihilation when the [chip limit button](../../implemented/feature/2026-10-05-chip-inventory-limit-preset.md) is pressed. The button selects every chip stage on weekdays permitted by the availability filter, preserves all existing selections and retains daily settings. Disabling the filter selects every chip stage on every weekday. Every row remains freely draggable after applying the preset.

## Simplification Review

The weekly editor owns the existing local-storage row order and shares it with the table through `v-model:stage-order`. The inventory component emits `chip-limits-applied`; the editor selects chips through `setStageForWeekday`, promotes rows and reuses `reorderWeeklyPlanStages`. Component-local migration state and duplicated order storage are removed. No backend schema or new store is required.

## Implementation and Verification

`CHIP_STAGES` derives the eight chip codes from existing presets and supplies both limit-rule filtering and priority promotion. Table-order merging preserves the chosen annihilation position and inserts new activities after the chip block that follows it. Every row, including annihilation, has a drag handle; no fixed-position move restriction applies. The editor persists order even when the table tab is unmounted.

Focused utility tests cover repeat promotion, all eight rows, preserved existing selections and daily settings, automatic chip selection with both availability-filter states, retained manual annihilation position and activity refresh. Component tests verify external row order, drag handles for all rows, retained manual annihilation position and button-event synchronization while the table is unmounted. Drag completion waits for the shared order to propagate before updating daily execution priority.

## Standards Findings

Pass. Existing stage presets, daily plan refs and local-storage keys remain authoritative. [INV-UI-06] is registered in the subsystem contract, coding standards and review checklist. The change uses existing terms without glossary edits.

## Spec Findings

Pass. Clicking the existing button sets chip limits and promotes all chip rows below annihilation. All chip stages are selected on eligible weekdays, and all existing selections remain valid. Other rows retain their relative order; every row remains draggable.
