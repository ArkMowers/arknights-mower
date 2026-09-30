---
title: 救急条件说明
status: implemented
category: simplification
date: 2026-09-30
---

# 救急条件说明

[English](2026-09-30-rescue-condition-help.md) | [中文](2026-09-30-rescue-condition-help.zh.md)

## 契约

选中救急条件时，条件选择框紧邻右侧显示现有 `HelpText` 问号按钮。提示内容包含 `rescue_condition_help` 和布尔表达式示例。弹窗不显示救急横幅或预设按钮。条件编辑、表达式序列化和排班行为遵循现有契约；不新增架构不变量或术语条目。

## 简化

横幅和行内段落重复同一说明。预设按钮是 `use_rescue_trigger` 的唯一调用者，编辑器重建键也没有其他使用者。删除横幅同时删除该处理函数、相关导入和重建状态。`HelpText` 提供与其他描述按钮一致的外观、悬停行为、键盘焦点和视口宽度限制。

## 验证

定向[救急表达式测试](../../../../ui/src/utils/trigger_rescue.test.js)、Vue 组件编译、格式检查和仓库治理检查验证保留的表达式契约与源码有效性。[原救急条件决策](../../implemented/feature/2026-09-30-rescue-backup-condition.zh.md)定义排班行为。

## 标准审查

通过：现有核心不变量继续成立。改动不新增持久状态或资源生命周期，并使用共享说明组件。治理检查及其 14 项测试、4 项子测试通过。

## 规格审查

通过：横幅已移除，救急选择框右侧按条件显示问号按钮。3 项救急表达式测试、Vue 编译、ESLint 和 Prettier 通过。
