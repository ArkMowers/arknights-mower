---
title: Rescue Scan Diagnostics
status: archived
category: bug-fix
date: 2026-10-04
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# 智能救急扫描诊断

## 契约

[INV-SCHED-09] 保持现有选人与派发行为。INFO 日志说明快照复用、补扫原因（最多八名干员）、每五页进度、完成或中断、选定替班及换班阻塞。扫描仍限制二十页和四十五秒。不增加扫描或重试任务。

## 简化与审查

诊断直接使用既有扫描及匹配分支，不新增报告抽象。[排班契约](../../../../docs/subsystems/base-scheduler.md) 定义选人规则。

Standards Findings：无未解决问题。既有预算、资格检查及清理保持不变；诊断姓名输出有数量上限。Ruff 通过。

Spec Findings：无未解决问题。240 项定向离线救急测试通过。日志区分快照选人、游戏内扫描、中断、候选不足、匹配冲突及任务窗口让行。
