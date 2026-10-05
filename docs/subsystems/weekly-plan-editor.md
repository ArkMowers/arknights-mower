# Weekly Plan Editor

## 1. State

The list and table editors share `maa_weekly_plan`. The weekly editor owns the row order saved under `maa-weekly-plan-table-stage-order` and shares it with the table through `v-model:stage-order`. The availability filter remains component state and controls weekday editing without rewriting saved selections.

## 2. Table Cells

`MaaWeeklyTable` applies one filtered availability predicate to cell styling, placeholders, editing and row-wide selection. Selected cells display `打`; selected stages remain removable when filtering is enabled.

## 3. Subsystem Invariants

- **[INV-UI-06] Pinned Annihilation Priority**: The weekly table always pins annihilation first; the chip-limit button promotes all eight chip rows immediately below it and synchronizes daily execution priority while preserving selected membership, other row order and daily settings.
- **[INV-UI-05] Chip Limit Preset Isolation**: The chip preset replaces each PR-A/B/C/D-1/2 limit rule with enabled AND conditions for its endpoint-provided drops at 5 small chips or 8 chip packs, without duplicating rules or changing other stage rules, weekly selections or inventory enablement.
- **[INV-UI-04] Weekly Availability Display**: Weekly table cells show unavailable placeholders and styling only while the availability filter is enabled; disabling it permits every weekday without changing saved selections.

The [availability display decision](../../.agents/notes/implemented/bug-fix/2026-10-04-weekly-availability-placeholder.md) records implementation and focused verification.

## 4. Inventory Limit Preset

The inventory panel's `一键芯片上限` button binds all eight chip stages using the stage-options endpoint's materials. PR-A/B/C/D-1 use a limit of 5 for each small chip; PR-A/B/C/D-2 use a limit of 8 for each chip pack. The button replaces existing rules for those stages with enabled AND rules and preserves other stage limits. It leaves selected membership and inventory enablement unchanged; rules apply only to stages selected in the active plan. Existing all-stages-reached fallback remains authoritative.

The same click promotes all eight chip rows immediately below annihilation and synchronizes the current plan's daily execution order. Other rows retain their relative order. Annihilation has no drag handle, and other rows cannot move above it. New activities follow any leading chip block; chip rows remain manually sortable. Saved order survives tab changes and reloads.

The [chip preset decision](../../.agents/notes/implemented/feature/2026-10-05-chip-inventory-limit-preset.md) records reuse and verification.

The [chip priority decision](../../.agents/notes/implemented/feature/2026-10-05-chip-stage-priority.md) records shared order ownership and verification.
