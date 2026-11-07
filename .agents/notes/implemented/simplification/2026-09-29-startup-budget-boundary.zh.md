---
title: 启动预算边界审查
status: implemented
category: simplification
date: 2026-09-29
---

# 启动预算边界审查

[English](2026-09-29-startup-budget-boundary.md)

`DeviceControl._io_budget()` 服务于启动、截图和恢复。`DeviceSession.ensure_ready()` 服务于启动、显式启动实例和恢复。两者均有多个生产调用点，需要保留。

截止时间初始化归 `DeviceSession.begin_budget()` 所有，由启动和就绪检查共用。该方法替换 `ensure_ready()` 中的内联初始化，避免 `_start()` 再次计算截止时间。不增加计时器、重试层或会话对象。这个小型共享方法在现有边界上明确预算归属，无需增加服务。

[启动契约](../bug-fix/2026-09-29-startup-recovery-budget.zh.md) 和 `arknights_mower/tests/device_session_tests.py` 定义并验证该行为。
