---
title: 复用现有 MuMu 返回键入口
status: implemented
category: simplification
date: 2026-09-28
---

# 复用现有 MuMu 返回键入口

[English](2026-09-28-reuse-mumu-back-dispatch.md) | [中文](2026-09-28-reuse-mumu-back-dispatch.zh.md)

`MuMuInputSession.back()` 提供原生 BACK 映射及有界工作进程分派。实现前对 `arknights_mower/` 和 `ui/src/` 的调用扫描记录该入口的生产调用方为零，且 `Device.send_keyevent` 对所有 Android 按键码均使用 ADB。

[原生 BACK 分派变更](../bug-fix/2026-09-28-mumu-native-back-dispatch.zh.md) 在选中 MuMu IPC 时复用此入口发送 Android BACK。审计没有发现需要删除的冗余抽象；复用不引入额外工作进程、按键映射表或重试机制。现有失败边界保留 `[INV-03]` 和 `[INV-04]`，并执行 `[INV-DEV-01]`。

定向离线验证使用 `device_touch_tests.py` 和 `device_mumu_input_tests.py` 检查分派及不重复输入的保证。
