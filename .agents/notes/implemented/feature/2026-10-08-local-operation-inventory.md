---
title: Local Operation Inventory
status: implemented
category: feature
date: 2026-10-08
---

# Local Operation Inventory

Local operation reuses the shared inventory delta writer and stage-limit evaluator. No parallel stock database, cloud refresh, or MAA battle dispatch is introduced. The scheduler reevaluates remaining stage selections after confirmed settlement and keeps daily tasks when all caps are reached.

**[INV-STOCK-02] Confirmed Local Battle Drops**: Local operation adds only stable, identified settlement quantities once per completed batch, never multiplies displayed totals by repeat count, holds cloud rebases while running, and stops the current stage at its configured inventory cap without cancelling other tasks.

The [local operation contract](../../../../docs/subsystems/local-operation.md) defines settlement recognition, batch receipt ownership, cloud protection and stopping semantics.
