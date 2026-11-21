---
title: Rescue Selection Page Restoration
status: archived
category: bug-fix
date: 2026-10-03
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# 救急选人页面恢复

## 契约

[INV-SCHED-09] 要求临时替班扫描先刷新设施产物，再打开驻员详情并进入选人页。产物巡检可能关闭驻员详情。扫描成功或失败均返回基建。

## 简化

扫描与正常房间回读采用相同顺序，复用 `turn_on_room_detail`。初次替班和组合重新评分共用该扫描，不增加辅助函数、重试策略、缓存或配置。[基建调度契约](../../../../docs/subsystems/base-scheduler.md) 是规则依据。

## 验证

离线页面状态模型在制造站和贸易站产物刷新时关闭驻员详情。两种情况均在修复前复现选人入口错误；控制中枢验证无需读取产物的情况。已有识别失败测试验证退出清理。

## 审查

Standards Findings：PASS。修改复用现有有界导航，保留退出清理和设备控制权；Ruff 与差异检查通过。

Spec Findings：PASS。制造站和贸易站扫描在产物巡检后恢复驻员详情，控制中枢扫描保持有效。聚焦离线测试通过 157 项及 4 项子测试，未运行真实设备集成测试。
