---
title: Group Binding Replacement Candidates
status: implemented
category: bug-fix
date: 2026-10-07
---

# Group Binding Replacement Candidates

一键替换的源干员菜单和目标已存在提示包含主副排班表所有列的替班干员。只出现在 `group_bindings[].replacement` 中的干员仍可选择。名单收集保留排班数据并去重；替换保留绑组名称和其他干员。

[INV-UI-10]

## 验证

定向测试覆盖只出现在主表或副表附加列的替班干员、拼音筛选、跨列共享名单、收集输入不变及选中干员在各绑定中的替换。旧单列和配置名单测试保留原有覆盖。

## 简化审计

两个生产调用方均使用 `collect_plan_operators`。现有 Set 提供去重，现有替换函数遍历附加绑定。名单收集使用相同的绑定遍历，不引入接口或变更持久数据。

## Standards Findings

通过。[INV-UI-10] 已登记到编辑器契约、编码标准和审查清单。名单收集不修改输入，仓库治理检查通过。

## Spec Findings

通过。只出现在主表或副表附加列的复现干员可以选择。现有替换函数更新全部匹配绑定并保留其他名单。前端定向测试 48 项全部通过。
