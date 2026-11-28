---
title: Release Planning Log Level
status: archived
category: bug-fix
date: 2026-10-04
---

# 离宿规划日志级别

由[初始化菲亚与离宿规划稳定性](../../implemented/bug-fix/2026-10-04-initial-fia-and-release-stability.zh.md)取代。复用未变的离宿任务，保留实际提前调整提示。

## 契约

[INV-SCHED-03] 保持个人心情上限离宿截止时间与操作窗口。重建离宿任务时，提前时间计算记录为 DEBUG 日志，不向用户宣告新的执行。

## 简化

共享清退规划器在恢复期间重建任务。现有 WebSocket 的 INFO 门槛过滤内部规划细节，不增加去重缓存或调度状态。

## 验证

截止时间及令夕测试通过 66 项，覆盖重复规划和截止时间变化。扩展个人上限测试通过 98 项，8 项救急退出失败在修改前的生产代码中同样复现。治理检查验证文档。

## Standards Findings

沿用日志边界，保持调度状态和资源归属；无需修改术语或配置。

## Spec Findings

重复提前计算保留在调试日志中，普通界面不再反复提示。
