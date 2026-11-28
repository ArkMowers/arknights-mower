---
title: Ordered growth crafting
status: implemented
category: feature
date: 2026-10-08
---

# Ordered growth crafting

Crafting and mastery execution use the same saved project order; skill training priority follows its skill subsequence. The queue exposes selected skill, module, unfinished explicit promotion and independent basic-skill projects through one dedicated configuration API. Active training plans retain a fixed prefix. Missing-material and preparation-only states remain visible without changing stored intent. Pure leveling produces no crafting row; implicit prerequisites remain inside their owning project. Module preparation includes only the promotion prerequisite through elite two level one, while actual unlock readiness and the material overview retain the full level requirement. The interface retains operator avatars and drag handles from the mastery plan list, with draft changes persisted by the unified plan save action. A separate leading reminder presents materials-ready unfinished projects, including pure leveling goals, without modifying their saved crafting order or requesting repeated production.

[INV-GROWTH-03] binds project ordering to minimum prerequisites and protected training reservations. [INV-GROWTH-01] accounts for shared costs once across admitted projects. [INV-SCHED-29] retains actual training readiness and the confirmed-training material boundary. The [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns API payloads, admission, persistence and user-interface behavior.

The [pre-flight simplification](../simplification/2026-10-08-shared-crafting-project-budget.md) uses existing material entries for both status and execution. Focused offline tests exercise custom permutations, locked-prefix rejection, prerequisite ordering and deduplication, shortage skipping, shared LMD and ingredients, continuation, and serialization of interface requests.
