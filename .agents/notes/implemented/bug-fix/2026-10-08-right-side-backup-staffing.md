---
title: Optional right-side backup staffing
status: implemented
category: bug-fix
date: 2026-10-08
---

# Optional right-side backup staffing

## Contract

[INV-SCHED-34] excludes reception, workshop, office, training and recycling from backup facility validation. Primary omissions and empty backup entries do not request staffing changes. Populated backup entries can introduce or extend right-side staffing; explicit tasks retain every supplied position. Left-side production facilities retain type, level, task and product checks. Center and dormitory constraints remain unchanged.

## Simplification and implementation

One fixed-capacity mapping identifies right-side rooms and supplies physical readback sizes. Existing roster and task merge functions support these rooms directly. Static `Current` entries preserve an existing corresponding roster slot; a missing source still fails ordinary roster validation. Empty overlays leave existing staff unchanged. No parallel selection or scheduling path is added.

## Verification

Offline regressions cover all five right-side facilities with absent, empty and partial primary staffing; backup roster, explicit task and combined forms pass startup validation and activation and produce complete final arrangements. Empty backup entries preserve staffing, task overlays extend partial pending targets, and existing production, dormitory and shift regressions remain required.
