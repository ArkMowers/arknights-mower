---
title: Workshop rejected recipes
status: implemented
category: bug-fix
date: 2026-10-08
---

# Workshop rejected recipes

Workshop admission and execution share transient recipe rejection records. A recipe rejected by the game is not retried with another worker against unchanged relevant inventory and configuration. Confirmed inventory deltas invalidate affected records; a completed inventory observation or a configuration generation change allows retries. Rejections never fabricate ingredient counts. Worker mood and Nine-Colored Deer phase selection do not reject recipes globally. Processing exceptions stop consecutive handoffs and restore borrowed staff.

The existing local blocked-material set retains mood filtering; the shared guard reuses existing admission and batch filtering rather than introducing a separate queue or persistent configuration. [INV-WORKSHOP-01] governs this boundary. Focused offline tests cover rejected recipes, unrelated work, refreshed inventory, and failure restoration.

The [growth contract](../../../../docs/subsystems/growth-planning.md) owns execution behavior.
