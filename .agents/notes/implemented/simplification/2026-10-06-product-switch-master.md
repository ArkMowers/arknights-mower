---
title: Product Switching Master Setting
status: implemented
category: simplification
date: 2026-10-06
---

# Product Switching Master Setting

## Contract

[INV-SCHED-27] makes `product_switching.enable` the master setting for manufacturing products, trade order types and their observations. The advanced-settings checkbox precedes the Grandet strategy. Disabled switching hides every subordinate setting and the facility-type, manufacturing-product, trade-order-type, production-statistics and their constant choices in backup conditions. Independent operator count, mastery-plan presence and training-state conditions remain available in the structured editor. Existing read-dependent condition expressions remain available as custom text without mutation. Ordinary shifts, collection and Grandet order runs retain their existing behavior. Orundum-material replenishment uses the effective Scheduling Plan product settings, including active backups, independently of the master setting and observed product cache.

## Simplification

The existing `grandet_mode` setting retains its five strategy consumers. One shared predicate gates task creation, pre-backup switching, pre-shift switching, batch execution, room observation and current-page observation. One cleanup operation removes dedicated switch tasks, releases deferred product reservations and makes retained staffing tasks eligible again. The scheduler performs cleanup before startup planning and infrastructure dispatch. The master setting defaults to enabled for legacy configurations; disabling it preserves all strategy values.

Facility types come from the actual room-title icon and observed-state cache, never Scheduling Plan configuration; unobserved types return unknown. The existing room detector and scheduler share the icon classifier. Type-only observations support Power Plants and clear old products when the facility type changes.

The condition editor observes the same configuration directly and loads facility-state data only while the master setting is enabled. It adds no independent UI configuration or persisted condition copy.

## Verification

The manufacture-switch tests cover both Grandet strategies while disabled, every switching entry, restored deferred tasks and reservations, independent trade order configuration, and legacy configuration round-trips. Frontend render tests verify hidden settings and read-dependent conditions, retained independent facility and training conditions, preserved expressions and restored values; configuration-store tests verify the complete default-enabled configuration, disabled-value serialization and saving only the master toggle. Replenishment regressions cover both shard recipes, both Grandet strategies while the master setting is disabled, conflicting observed products and backup activation and deactivation without product reads or switches. Facility regressions cover unobserved types, conflicting plan and observed types, Power Plants, backup activation and type-only cache updates. Existing product-switch, shift-convergence and scheduler-wakeup tests retain enabled behavior.

## Standards Findings

PASS. [INV-SCHED-27] is registered in the subsystem contract, coding standards and review checklist. The approved bilingual glossary text documents the master setting. The change adds no device operations or resource lifecycle; configuration remains persisted through the existing store. Targeted Ruff, ESLint and governance checks pass.

## Spec Findings

PASS. The master checkbox precedes the Grandet strategy and hides all subordinate settings while disabled. Every automatic switch and related observation boundary checks the master setting; deferred staffing survives reservation cleanup. Both Grandet strategies retain their original enabled behavior. Existing expressions and strategy values survive toggling. The manufacture-switch and room-detection suites pass with 179 tests; frontend render, data-loading, condition, configuration and partial-save suites pass with 66 tests. Shift-convergence, scheduler-wakeup and governance checks retain their verified behavior.
