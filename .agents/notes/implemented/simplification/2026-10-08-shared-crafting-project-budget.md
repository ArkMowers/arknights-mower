---
title: Shared crafting project budget
status: implemented
category: simplification
date: 2026-10-08
---

# Shared crafting project budget

`growth.material_entries` supplies both aggregate plan calculation and project preparation. Its optional prerequisite split exposes the ordering boundary without adding standalone prerequisite projects. Crafting projects normalize promotion targets to destination-phase level one before using those entries; the material overview retains full level targets. `growth_order.prepare_project_materials` has two production consumers: the queue status response and workshop configuration. Both use the same cumulative admission result rather than calculating readiness independently.

The existing single-skill legacy helper is not restored as an automatic preparation path. `growth_workshop.next_recipe` retains recipe decomposition, stock limits and permitted-material policy. Project ordering changes its input entries instead of creating a second recipe allocator. The implementation reduces distinct calculation paths rather than promising a source-line reduction.

[INV-GROWTH-01] and [INV-GROWTH-03] preserve shared stock and prerequisite semantics. The [ordered crafting decision](../feature/2026-10-08-ordered-growth-crafting.md) owns the feature boundary, and the [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns admission rules. Focused material, ordering and workshop continuation tests cover shared ingredients, fees, skipped projects and confirmed-batch recalculation.
