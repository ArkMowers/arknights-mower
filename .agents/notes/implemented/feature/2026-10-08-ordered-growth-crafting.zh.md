---
title: Ordered growth crafting
status: implemented
category: feature
date: 2026-10-08
---

# 养成项目合成顺序

合成使用独立的项目队列，专精执行保留数据库计划优先级。队列通过专用配置接口提供已选技能、模组、显式等级及独立基础技能项目。进行中的训练计划固定在队首。材料不足和仅备料的状态保持可见，不改变已保存的养成意图。

[INV-GROWTH-03] 将项目顺序约束到最低前置与受保护的训练材料预留。[INV-GROWTH-01] 保证已准入项目之间的共用费用只计算一次。[INV-SCHED-29] 保留实际训练条件和已确认开训计划的材料边界。[子系统契约](../../../../docs/subsystems/growth-planning.md) 统一定义接口载荷、准入、持久化和界面行为。

[前置简化](../simplification/2026-10-08-shared-crafting-project-budget.zh.md) 为状态展示与执行复用现有材料条目。定向离线测试覆盖自定义排列、锁定前缀拒绝、前置顺序及去重、缺料跳过、共用龙门币及原料、连续加工和界面请求串行。
