---
title: Single Trade Order Admission Cursor
status: implemented
category: simplification
date: 2026-10-08
---

# Single Trade Order Admission Cursor

## Contract

[INV-SCHED-36] advances one scheduling cursor through queued operations and scheduled waiting. A failed admission retains the accepted prefix and moves the dependent suffix after the trade order.

## Caller Evidence

`scheduling` calls `_schedule_run_orders` once; six solver scheduling sites share this entry. The nested suffix scan repeatedly adds already counted tasks. One ordered cursor replaces that scan and retains maintenance adjustment, close-order reporting and deferred dorm composition. Direct queue reconciliation also retains newly split tasks alongside protected tasks. No external API requires the internal scan.

## Impact

The replacement removes repeated accumulation and the fixed ten-minute admission cutoff. Existing occupancy projection and bounded operation measurements provide the required data without another projection model or configuration schema.

## Verification

Offline scheduling tests cover repeat admission, future starts, deferred backlog and protected task coexistence.
