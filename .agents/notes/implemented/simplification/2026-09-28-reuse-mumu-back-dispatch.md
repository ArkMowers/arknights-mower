---
title: Reuse the Existing MuMu Back Entry Point
status: implemented
category: simplification
date: 2026-09-28
---

# Reuse the Existing MuMu Back Entry Point

[English](2026-09-28-reuse-mumu-back-dispatch.md) | [中文](2026-09-28-reuse-mumu-back-dispatch.zh.md)

`MuMuInputSession.back()` provides native BACK mapping and bounded worker dispatch. The pre-flight caller scan across `arknights_mower/` and `ui/src/` records zero production callers for this entry point before the change and ADB dispatch for every Android keycode in `Device.send_keyevent`.

The [native BACK dispatch change](../bug-fix/2026-09-28-mumu-native-back-dispatch.md) reuses this entry point for Android BACK with MuMu IPC selected. The audit identifies no redundant abstraction requiring removal; reuse requires no additional worker, key mapping table, or retry mechanism. The existing failure boundary preserves `[INV-03]` and `[INV-04]` while enforcing `[INV-DEV-01]`.

Focused offline verification uses `device_touch_tests.py` and `device_mumu_input_tests.py` to check dispatch and absence of replay.
