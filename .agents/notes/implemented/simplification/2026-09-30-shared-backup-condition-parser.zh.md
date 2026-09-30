---
title: Shared Backup Condition Parser
status: implemented
category: simplification
date: 2026-09-30
---

# Shared Backup Condition Parser

[English](2026-09-30-shared-backup-condition-parser.md) | [中文](2026-09-30-shared-backup-condition-parser.zh.md)

## 契约

副表能力依据条件语法中的实际`op_data`方法调用。字符串常量不授予能力。[维护执行顺序说明](../feature/2026-09-30-maintenance-backup-ordering.md)和现有救急条件共用此规则。

## 证据与实现

前置简化审查确认`Plan.uses_rescue_condition`中的现有 AST 识别可用于两种实际条件能力。`Plan.uses_condition`负责解析及调用识别，救急与维护属性分别提供一个方法名。实现避免复制识别逻辑，不增加配置注册表，不改变表达式求值。两个属性均在干员排班合并与校验中有生产调用。

## 验证

现有救急测试与维护测试覆盖嵌套调用、无效条件及包含方法名的字符串常量。领域定义与持久化结构不变。
