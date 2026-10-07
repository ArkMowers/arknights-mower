---
title: Local Inventory Execution
status: implemented
category: simplification
date: 2026-10-08
---

# Local Inventory Execution

Two scheduler call sites remove unconditional Skland refreshes: workshop entry and inventory stage selection. Both consume the shared inventory already maintained by scans and confirmed crafting. MAA cumulative drop receipts use the same protected delta writer. This removes competing remote baselines from execution.

**[INV-MAA-05] Local Inventory Execution**: Workshop execution and inventory stage selection use persisted local stock without fetching Skland; accepted MAA cumulative drops update that stock once per task, and configured stage caps stop only the reached Fight task while preserving automatic series and subsequent tasks.

The [MAA contract](../../../../docs/subsystems/maa-integration.md) owns callback accounting, cloud holds, AND/OR cap handling and automatic series behavior. Offline tests cover duplicate receipts, stale and leading cloud snapshots, invalidated stock, live target updates and all-capped plans.
