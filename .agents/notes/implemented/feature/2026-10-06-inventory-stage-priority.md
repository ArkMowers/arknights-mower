---
title: Inventory Stage Priority
status: implemented
category: feature
date: 2026-10-06
---

# Inventory Stage Priority

## Contract

[INV-MAA-04] keeps selected annihilation first and defers stages without active inventory rules while a selected inventory-bound stage remains below its limits. When every selected bound stage is skipped, ordinary stages supply the fallback even when annihilation remains. Backend dispatch and frontend preview agree without changing saved selections.

Enabled rules with identified items and positive limits bind stages; enabled ratio members with identified items and positive weights also bind stages. Limits apply before ratios. Disabled rules, empty conditions and zero values do not bind. Last-operation selection is an ordinary fallback. With only capped stages and no remaining candidate, the existing whole-plan fallback remains authoritative.

## Simplification Review

The backend selection function has two scheduler consumers: MAA Fight dispatch and local operation planning. The frontend preview mirrors it. Both reuse existing limit evaluation to determine active bindings and one ratio-member predicate for priority and ratio selection. No configuration fields, store or scheduler wrappers are added.

## Verification

Focused backend selection, scheduler dispatch and frontend preview tests cover partial and complete chip limits, annihilation coexistence, last-operation fallback, inactive rules, ratio-only bindings, ratio tie order and unchanged source plans. Governance and documentation checks verify the invariant registration and decision triplet. Existing domain terms remain unchanged; no glossary edits are required.

## Standards Findings

Pass. [INV-MAA-04] is registered in the subsystem contract, coding standards and review checklist. Existing configuration and snapshot boundaries remain authoritative. Governance gates and their 14 focused tests pass; source lint and diff whitespace checks pass.

## Spec Findings

Pass. Partial chip limits send only annihilation and surviving chips; complete selected chip limits admit the selected ordinary fallback. MAA and local dispatch share the result. Selection, scheduler and route tests pass (89 tests), as do frontend inventory and weekly-editor tests (45 tests). Inventory enablement without rules prioritizes annihilation without fetching a snapshot; disabled selection retains the source order.
