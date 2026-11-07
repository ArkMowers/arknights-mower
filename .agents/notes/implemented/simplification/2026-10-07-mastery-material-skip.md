---
title: Mastery Material Candidate Selection
status: implemented
category: simplification
date: 2026-10-07
---

# Mastery Material Candidate Selection

## Contract

[INV-SCHED-29] skips idle skills whose remaining target costs cannot be supplied from stock and permitted crafting, preserves plan state and priority, and reevaluates readiness after refreshed inventory. Confirmed training retains its remaining-material reservation.

## Simplification Evidence

`compute_workshop_config` serves automatic configuration and depot-scan updates through `update_workshop_config`. Candidate selection and material readiness share one bounded pass over the existing ordered plans and one material budget. A missing-material candidate does not terminate selection. The change removes the unused local `item_rarity` function and adds no persistent flag, timer or configuration. Existing glossary definitions remain accurate.

## Verification

Offline readiness tests cover a missing-material head followed by a craftable skill, all candidates unavailable, stock refresh restoring the original priority, target-level costs and confirmed-training reservations. Automatic configuration and depot scans use the same candidate selection.
