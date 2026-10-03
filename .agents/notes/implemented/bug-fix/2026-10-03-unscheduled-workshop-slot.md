---
title: Workshop tasks without static workshop staff
status: implemented
category: bug-fix
date: 2026-10-03
---

# Workshop tasks without static workshop staff

## Contract

[INV-SCHED-18] gives the workshop one physical slot independently of its Scheduling Plan entry. Absent entries, empty staff lists, and populated entries all permit task-specific workshop arrangements and actual occupant readback. Neither cache reads nor task execution inserts static workshop staff. Training retains two physical slots; other facilities retain their configured capacities.

## Simplification audit

The shared cache reader and room reader already distinguish the training room by physical capacity. Both workshop consumers use these existing paths. Extending those branches removes the plan-length dependency without another room registry, fallback plan, configuration field, or selection implementation.

## Implementation

`Operators.get_current_room` returns the cached workshop slot. `BaseSchedulerSolver.get_agent_from_room` reads the physical workshop slot and updates actual occupancy and mood through the existing reader. Crafting admission, consecutive batches, staff restoration, and dormitory recovery remain authoritative. Existing domain glossary definitions remain unchanged.

Before the first selection in each crafting batch, `_craft_material` reads the actual workshop occupant to establish the restoration snapshot. Missing occupancy cache never establishes vacancy. A confirmed vacant workshop retains the first crafter under the existing rule; consecutive tasks reuse the initial snapshot.

The workshop reader establishes vacancy only from the empty-slot marker. An unknown occupant name uses the existing three-read limit with two 0.25-second waits; exhaustion raises `RecognizeError` before clearing occupancy caches or establishing a restoration snapshot. Initial observation errors propagate through the scheduler's existing error handling without selecting, crafting, or consuming the pending task. No fallback occupant or separate recovery flow substitutes for a recognition error.

## Verification

Offline regressions cover absent, empty, populated, and oversized workshop lists; vacant and occupied slots; unchanged Scheduling Plans; actual room arrangements and confirmation readback; consecutive crafting and restoration; and unchanged training and ordinary facility capacities. The pre-fix cache and reader regressions reproduce missing-room errors and zero-length reads.

Actual arranging and room-reader regressions separate physical occupants from cached positions, cover uncached residents and stale occupied caches on a vacant workshop, require readback before the first selection, and verify the original resident and borrowed dormitory positions after consecutive crafting.

Recognition regressions cover recovery on the second and third name reads and exhausted retries with both cached and uncached residents. Through the real `infra_main` dispatch entry, unknown names report an error and preserve actual occupancy, cached positions, Scheduling Plans, and pending tasks without selection or confirmation; a subsequent dispatch with successful recognition completes crafting and restoration.
