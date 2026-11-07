---
format: decision
title: Workshop planning path
status: implemented
category: simplification
date: 2026-10-13
---

# Workshop planning path

Configuration generation and status share the active growth projection; execution checks return structured blockers. This decision accompanies [responsive dispatch](../feature/2026-10-13-workshop-responsive-dispatch.md). The [growth contract](../../../../docs/subsystems/growth-planning.md) owns current behavior.

## Problem

Two unused configuration generators still had direct tests that did not establish current multi-project preparation behavior. Status also needs the same calculation as actual crafting.

## Decision

`calculate_workshop_plan` calls `growth_workshop_config`, which uses ordered project preparation and `next_recipe`. Status consumes the same projection with one supplied inventory snapshot. Admission and diagnostics share `workshop_admission_block`; pre-arrangement verification retains the material and operator checks. Messages derive from structured results rather than parsed logs.

The unused `compute_workshop_config`, `compute_default_workshop_config`, `_workshop_lookahead_active` and `_workshop_training_reserve` functions are removed after a repository caller audit. These four functions account for 348 source lines before import and test changes. `_remaining_mastery_materials` stays because mastery dispatch calls it in production. No second planner, event history, worker or queue is introduced.

## Coverage and compatibility

Applicable helper tests now exercise the real growth projection and configuration route. Direct allocator tests use explicit fixture recipes. Target costs, training reservations, material protection, unavailable BOX data, specialist allocation and manual restoration retain coverage. Superseded single-skill lookahead assertions are removed; ordered multi-project tests define the active contract. Indirect ingredient tests repeatedly select `next_recipe` and apply confirmed deltas to verify exact total production.

The focused backend run passes 830 tests, including migrated workshop and mastery suites. Repository Python imports contain no removed function references. The removal has no identified production caller; undocumented external imports remain a compatibility limitation.



## Alternatives considered

Keeping the old generators as test entry points continues to verify a separate algorithm. Migrating tests to the actual growth projection directly covers reservations and route behavior. The paid-stage helper still has a production caller and cannot be removed with the generators.

## Consequences

Configuration and status share planning, and tests no longer depend on unused generators. Undocumented external imports may break; this change provides no compatibility wrapper. Reintroducing one requires evidence of a real external caller.
