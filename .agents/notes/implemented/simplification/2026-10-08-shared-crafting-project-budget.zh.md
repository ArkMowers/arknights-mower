---
title: Shared crafting project budget
status: implemented
category: simplification
date: 2026-10-08
---

# 复用养成项目材料预算

`growth.material_entries` 同时提供整体计划计算与项目备料的材料条目。可选的前置拆分明确材料顺序边界，不新增独立前置项目。合成项目先将精英化目标归一到目标阶段一级，再使用这些条目；材料总览保留完整等级目标。`growth_order.prepare_project_materials` 有两个生产调用方：队列状态响应和加工配置。两者使用相同的累计准入结果，不分别计算材料是否充足。

原有单技能辅助函数不重新成为自动备料路径。`growth_workshop.next_recipe` 保留配方分解、库存上下限和允许材料策略。项目排序只调整其输入条目，不另建一套配方分配器。实现减少独立计算路径，不承诺减少代码行数。

[INV-GROWTH-01] 与 [INV-GROWTH-03] 保持共用库存和前置语义。[合成顺序决策](../feature/2026-10-08-ordered-growth-crafting.zh.md) 定义功能边界，[子系统契约](../../../../docs/subsystems/growth-planning.md) 定义准入规则。定向材料、排序和连续加工测试覆盖共用原料、费用、跳过项目和确认加工后的重算。
