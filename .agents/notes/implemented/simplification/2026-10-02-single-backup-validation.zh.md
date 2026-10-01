---
title: Single Backup Validation Path
status: implemented
category: simplification
date: 2026-10-02
---

# Single Backup Validation Path

[English](2026-10-02-single-backup-validation.md) | [中文](2026-10-02-single-backup-validation.zh.md)

## 契约

[副表校验契约](../../../../docs/subsystems/base-scheduler.md)定义 **[INV-SCHED-16] 副表校验覆盖**。手动校验与启动使用 `Operators.validate_backup_plans`；合并配置使用与换班预演相同的 `swap_plan(..., refresh=True)` 检查。

## 简化审计

仓库搜索确认 `Operators.validate_backup_plans` 有两个调用方：校验 HTTP 接口与启动入口。`validate_backup_plans_offline` 没有调用方，重复实现主力名称关联图，却只检查干员重复。`Plan.primary_names` 仅供这两套校验关联图使用；文档没有声明这两个闲置接口为公开契约。

校验器根据受支持的触发条件逻辑生成可能开关组合，不再根据主力名称推断独立性。删除闲置重复校验器及其主力名称辅助方法。校验最多接受 16384 种不同组合和 262144 种符号状态，超过上限返回校验未完成错误。候选模型在配置检查前清空实际驻员缓存。独立干员模型保留实际驻员与当前排班。调度执行及配置结构保持原有契约。

## 验证

[离线回归测试](../../../../arknights_mower/tests/backup_validation_tests.py)覆盖跨副表替班冲突、三张副表组成的床位容量冲突、覆盖顺序、状态隔离、组合上限、二维码解出的六张副表排班及二十张副表的换班预演。[条件分析测试](../../../../arknights_mower/tests/backup_condition_coverage_tests.py)覆盖保守排除与符号状态准入。
