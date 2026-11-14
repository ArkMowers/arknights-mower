---
title: 低心情预估候选分类
status: implemented
category: simplification
date: 2026-10-02
---

# 低心情预估候选分类

## 契约

共用 `DormCandidates` 快照区分具有有效低心情选人卡片预估的合格未知候选与实读恢复候选。扫描、空床补位和实际选人共用这一分类。预估沿用现有有效期、资格检查和 [INV-SCHED-15] 实读隔离要求。占用床位的准入遵循 [INV-SCHED-43]：预估子集本身不授予替换资格，也不解除满员兜底保留。

## 简化证据

`dorm_candidates` 一次计算低心情预估子集，供 `_plan_primary_recovery`、`try_add_release_dorm` 和 `dorm_mood_fallback_candidates` 共用。同一快照消除重复的预估分类，但不独立授予接管资格。替换规划只允许前四层受保护预估候选参与合法的低层级接管，其他预估候选等待空床准入。不增加持久化标记或设备扫描。

[替换决策](../bug-fix/2026-10-02-estimated-idle-replacement.zh.md) 定义行为和专项测试。现有术语定义已经允许选人卡片筛选，并禁止其建立实读恢复状态。
