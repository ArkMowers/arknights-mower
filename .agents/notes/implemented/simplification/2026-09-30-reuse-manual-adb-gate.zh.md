---
title: 为 MuMu Pro 复用手动 ADB 检测
status: implemented
category: simplification
date: 2026-09-30
---

# 为 MuMu Pro 复用手动 ADB 检测

[English](2026-09-30-reuse-manual-adb-gate.md) | [中文](2026-09-30-reuse-manual-adb-gate.zh.md)

## 契约

`PreflightService` 已验证精确 ADB serial、Android 就绪状态、游戏包和实际画面。实例状态未知时，`DeviceSession` 已使用 `last_serial`。MuMu Pro 手动绑定无需另建端点解析器或连接回退。

## 证据

手动填写 serial 时，`ProductionSimulator` 返回未知实例状态，由共用 ADB 检测验证这一精确目标。另有只读管理工具查询支持[已核验的实例选择](../feature/2026-09-30-mumu-pro-instance-selection.zh.md)。移除预检和会话的无条件拒绝后，现有只读检测可直接复用；旧停机入口增加一处防护，阻止未经核验的管理命令。

[设备契约](../../../../docs/subsystems/device-control.md)规定最终绑定行为。
