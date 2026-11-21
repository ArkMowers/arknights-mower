---
title: Backup Replacement State Preservation
status: implemented
category: simplification
date: 2026-10-06
---

# Backup Replacement State Preservation

[INV-SCHED-28], [INV-UI-09]

Replacement-list-only backup changes reuse the existing complete replacement matcher and backup transition boundary. A separate per-binding mode and event state are unnecessary: backup conditions select the replacement lists. The two transition callers cover normal backup checks and shift projection. Available replacements preserve working or resting primary state, beds and recovery deadlines. The [product rest state decision](2026-10-06-backup-product-rest-state.md) extends this boundary to product changes and defines early recalls when replacements are insufficient. Explicit staffing tasks, primary changes and binding membership changes retain existing behavior.

The editor keeps only the add button on the first binding row and offers a deep copy of one main-plan facility into the selected backup.

## Verification

Focused offline tests cover entry, exit, multiple-group active bindings, matching conflicts, reserved or busy covers, dormitory beds and projection rollback. Frontend tests cover import isolation and button visibility.
