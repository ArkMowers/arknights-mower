# Weekly Plan Editor

## 1. State

The list and table editors share `maa_weekly_plan`. The availability filter remains component state and controls weekday editing without rewriting saved selections.

## 2. Table Cells

`MaaWeeklyTable` applies one filtered availability predicate to cell styling, placeholders, editing and row-wide selection. Selected cells display `打`; selected stages remain removable when filtering is enabled.

## 3. Subsystem Invariants

- **[INV-UI-04] Weekly Availability Display**: Weekly table cells show unavailable placeholders and styling only while the availability filter is enabled; disabling it permits every weekday without changing saved selections.

The [availability display decision](../../.agents/notes/implemented/bug-fix/2026-10-04-weekly-availability-placeholder.md) records implementation and focused verification.
