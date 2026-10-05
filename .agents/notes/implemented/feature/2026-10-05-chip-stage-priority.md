---
title: Chip Stage Priority
status: implemented
category: feature
date: 2026-10-05
---

# Chip Stage Priority

## Contract

[INV-UI-06] keeps annihilation at the top of the weekly table and promotes all eight chip rows immediately below it when the [chip limit button](../../implemented/feature/2026-10-05-chip-inventory-limit-preset.md) is pressed. Each day's selected stages follow that priority without selecting additional stages or changing daily settings.

## Simplification Review

The weekly editor owns the existing local-storage row order and shares it with the table through `v-model:stage-order`. The inventory component emits `chip-limits-applied`; the editor promotes rows and reuses `reorderWeeklyPlanStages`. Component-local migration state and duplicated order storage are removed. No backend schema or new store is required.

## Implementation and Verification

`CHIP_STAGES` derives the eight chip codes from existing presets and supplies both limit-rule filtering and priority promotion. Table-order merging pins annihilation, inserts new activities after any leading chip block and preserves other row order. Annihilation has no drag handle; move validation rejects insertion above it. The editor persists order even when the table tab is unmounted.

Focused utility tests cover repeat promotion, all eight rows, unchanged selected membership and daily settings, restored annihilation priority and activity refresh. Component tests verify external row order, the absent annihilation drag handle, drag restrictions and button-event synchronization while the table is unmounted. Drag completion waits for the shared order to propagate before updating daily execution priority.

## Standards Findings

Pass. Existing stage presets, daily plan refs and local-storage keys remain authoritative. [INV-UI-06] is registered in the subsystem contract, coding standards and review checklist. The change uses existing terms without glossary edits.

## Spec Findings

Pass. Clicking the existing button sets chip limits and promotes all chip rows below pinned annihilation. Other rows retain their relative order; chip rows remain draggable and existing selected membership is preserved.
