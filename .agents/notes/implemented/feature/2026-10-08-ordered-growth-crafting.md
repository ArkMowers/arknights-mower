---
title: Ordered growth crafting
status: implemented
category: feature
date: 2026-10-08
---

# Ordered growth crafting

Crafting uses an independent project queue while mastery execution retains database plan priority. The queue exposes selected skill, module, explicit level and independent basic-skill projects through one dedicated configuration API. Active training plans retain a fixed prefix. Missing-material and preparation-only states remain visible without changing stored intent.

[INV-GROWTH-03] binds project ordering to minimum prerequisites and protected training reservations. [INV-GROWTH-01] accounts for shared costs once across admitted projects. [INV-SCHED-29] retains actual training readiness and the confirmed-training material boundary. The [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns API payloads, admission, persistence and user-interface behavior.

The [pre-flight simplification](../simplification/2026-10-08-shared-crafting-project-budget.md) uses existing material entries for both status and execution. Focused offline tests exercise custom permutations, locked-prefix rejection, prerequisite ordering and deduplication, shortage skipping, shared LMD and ingredients, continuation, and serialization of interface requests.
