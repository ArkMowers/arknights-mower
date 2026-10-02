---
title: 低心情预估候选分类
status: implemented
category: simplification
date: 2026-10-02
---

# 低心情预估候选分类

## 契约

共用 `DormCandidates` 快照区分具有有效低心情选人卡片预估的合格未知候选与实读恢复候选。扫描、普通替换规划和实际选人共用这一分类。预估沿用现有有效期、资格检查和 [INV-SCHED-15] 实读隔离要求。

## 简化证据

`_plan_primary_recovery` 重复计算预估阈值，而 `try_add_release_dorm` 与 `dorm_mood_fallback_candidates` 只使用实读恢复或一般未知状态。`dorm_candidates` 一次计算低心情预估子集，替代规划入口的独立阈值循环，并向入队与选人提供同一快照。不增加持久化标记或设备扫描。

[替换决策](../bug-fix/2026-10-02-estimated-idle-replacement.zh.md) 定义行为和专项测试。现有术语定义已经允许选人卡片筛选，并禁止其建立实读恢复状态。
