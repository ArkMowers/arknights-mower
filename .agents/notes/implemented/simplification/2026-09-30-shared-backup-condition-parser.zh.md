---
title: Shared Backup Condition Parser
status: implemented
category: simplification
date: 2026-09-30
---

# 共享副表条件解析

## 契约

副表能力由条件语法中实际的 `op_data` 方法调用确定，字符串常量不授予能力。`Plan.uses_condition` 负责解析和调用识别，用于[维护切表契约](../feature/2026-09-30-maintenance-backup-ordering.zh.md)。退役救急调用由配置语法树迁移处理，不进入运行期表达式求值。

## 验证

维护与退役条件迁移测试覆盖嵌套调用、无效表达式及方法名字符串常量。[Mower 自动救急恢复](../../implemented/simplification/2026-10-02-native-automatic-rescue.zh.md) 定义退役救急能力的替代契约。
