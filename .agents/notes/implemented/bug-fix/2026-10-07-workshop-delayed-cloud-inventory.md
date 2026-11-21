---
title: Workshop delayed cloud inventory
status: implemented
category: bug-fix
date: 2026-10-07
---

# Workshop delayed cloud inventory

A successful cloud request can still carry delayed material counts. Request-start timestamps cannot supersede confirmed workshop output and consumption. Persistent pending baselines and change directions protect each affected item. Production-only cloud counts reconcile at or above predicted stock; consumption-only counts reconcile at or below it. Items both produced and consumed, and migrated entries with unknown directions, require exact equality with predicted cloud stock or a newer actual warehouse reading that covers the item. Partial scans never treat an absent item as an observed zero. The same database serves all workshop operators, manual crafting and growth planning. Upper and lower limits are absolute inventory thresholds. Regression tests reproduce three fiberboards, three ketone arrays and one oriron block across repeated delayed requests.

[INV-STOCK-01] also covers intermediate materials that are produced and then consumed: a delayed count from between those operations cannot discard the confirmed final inventory. Regression tests cover two-way changes and persistence across restart.
