---
title: Startup Budget Boundary Audit
status: implemented
category: simplification
date: 2026-09-29
---

# Startup Budget Boundary Audit

[中文](2026-09-29-startup-budget-boundary.zh.md)

`DeviceControl._io_budget()` serves startup, capture and recovery. `DeviceSession.ensure_ready()` serves startup, explicit instance launch and recovery. Both interfaces have multiple production callers and remain necessary.

Deadline initialization belongs to `DeviceSession.begin_budget()`, shared by startup and readiness. This replaces the inline initialization in `ensure_ready()` and avoids a second deadline calculation in `_start()`. No additional timer, retry layer or session object is required. The small shared method exposes budget ownership across the existing boundary rather than introducing another service.

The [startup contract](../bug-fix/2026-09-29-startup-recovery-budget.md) and `arknights_mower/tests/device_session_tests.py` define and verify the behavior.
