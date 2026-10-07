---
title: Unified growth plan order
status: implemented
category: simplification
date: 2026-10-08
---

# Unified growth plan order

The former page-level plan modal and `GrowthCraftingOrder` expose separate editing surfaces for the same targets. The page-level goal list has no draggable binding. One component now owns a complete ordered draft of skills, promotion, basic skills, modules and pure-level goals. This removes the page modal and its duplicate removal, sorting and save state rather than adding a third goal-order store.

The existing `growth_crafting_order` field is the sole mixed-order persistence source. Its crafting projection omits pure-level goals; its skill subsequence sets training priority when saved. Active training remains a fixed prefix. [INV-GROWTH-03] covers order synchronization, prerequisite preparation and protected reservations; [INV-GROWTH-01] preserves shared material budgets. Validation rejects stale sets and persistence failures preserve order. Explicit deletion uses existing APIs, with partial failures shown and reconciled against the server. Materials-ready manual goals appear only in the leading reminder; the sortable projection omits them without deleting their saved intent.

The [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns payloads and interface behavior. Focused backend and component tests cover mixed orders, pure-level display, locked rows, canceled drafts and save failures. No glossary or credential changes occur.

Quick-added skills retain the saved sequence before dispatch, appending new skills instead of regrouping existing operators.
