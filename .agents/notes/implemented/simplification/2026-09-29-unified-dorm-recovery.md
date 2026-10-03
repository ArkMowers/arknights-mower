---
title: Unified dormitory recovery
status: implemented
category: simplification
date: 2026-09-29
---

# Unified dormitory recovery

## Contract

All scheduling uses one Dormitory Recovery policy. Retired experimental, workshop-rest-priority, initialization-restart, and backup-timing settings do not select alternate behavior. Older configuration files remain importable. Configuration and UI expose only active settings.

[INV-SCHED-07] Unified Dormitory Policy requires the same scheduling behavior regardless of retired mode keys. [INV-SCHED-02] preserves the Single-Target Recovery Target at its final slot throughout temporary selection and roster restoration. Earlier non-manager slots retain confirmed full residents or use the highest-mood eligible idle operators. Actual readback must confirm competitors cannot take the target's recovery before recording the assignment. Missing candidates or failed reads preserve the final roster and do not mark an unverified recovery assignment.

## Simplification evidence

The experimental flag selected parallel implementations throughout `base_schedule`, `operators`, and `scheduler_task`, with duplicate UI explanations and initialization paths. Removing these branches retains the converged shift planner, slot ownership checks, mood-limit releases, candidate exclusions, and deadline guards as the sole implementations. No constant-true compatibility mode remains.

## Verification

Focused offline scheduling tests cover backup convergence, admission, initialization, charging, release deadlines, legacy configuration imports, and stable target placement with non-full padding. Frontend configuration tests and a production build verify the removed controls and retained settings.
