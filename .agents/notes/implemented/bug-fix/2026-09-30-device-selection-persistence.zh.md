---
title: 设备实例选择持久化
status: implemented
category: bug-fix
date: 2026-09-30
---

# 设备实例选择持久化

## 契约

[INV-UI-03] Selected Instance Persistence 要求从检测结果选择实例时，在测试连接或启动之前保存明确选定的实例身份。连接失败保留该选择，不保存未经验证的端点或游戏包。身份保存失败时不执行生命周期操作，并保留原先保存的 Device Profile。候选列表仍为临时状态。

## 边界与简化

`DeviceSettings.bindInstance` 复用 `saveDiscoveredDevice`，不再维护另一份身份字段投影。所选实例编号及身份核验字段与连接就绪状态分别持久化。手动编辑的身份字段仍在验证成功前保留为草稿。启动确认要求保持不变。

## 验证

组件测试覆盖多个候选、启动失败后显式重试，以及身份保存被拒绝。会话测试覆盖 Recovery Budget 耗尽后的新启动：动作计数和截止时间重置，所选身份不变。同一事务保留原有预算。
