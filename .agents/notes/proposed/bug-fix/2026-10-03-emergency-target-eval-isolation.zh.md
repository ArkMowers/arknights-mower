---
title: Intelligent Rescue Target Evaluation Isolation
status: proposed
category: bug-fix
date: 2026-10-03
---

# 智能救急目标求值隔离

## 契约

[INV-SCHED-09] 在恢复目标推演中复用只读的表达式求值模型。可变的干员、宿舍床位、排班与配置保持隔离，不修改运行状态。求值注入的内建对象和扩展句柄不要求序列化。

## 简化

目标计算沿用完整换班预演的 deepcopy memo 方式，不增加辅助函数、缓存、状态字段或兼容路径。[基建调度契约](../../../../docs/subsystems/base-scheduler.md) 是不可违反规则的依据。

## 验证

离线回归向求值模型注入实际 PyCapsule，执行表达式求值，并通过原生恢复机会探针运行真实目标计算。验证求值模型身份、可变状态隔离与历史目标计算。同一测试在修复前因 PyCapsule 复制错误而失败。已有真实副表退出交接回归继续执行。

## 审查

Standards Findings：等待独立审查。

Spec Findings：等待独立审查。
