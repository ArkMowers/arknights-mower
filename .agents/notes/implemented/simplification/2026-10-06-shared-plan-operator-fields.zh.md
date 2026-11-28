---
title: 共享排班干员字段
status: implemented
category: simplification
date: 2026-10-06
---

# 共享排班干员字段

## 契约

[INV-SCHED-26] 保持旧副表的名单添加规则和来源设置隔离，同时支持移除名单。

## 简化

排班存储使用 OPERATOR_CONF_FIELDS 执行添加名单转换、移除名单转换、干员替换和干员收集，删除 backup_conf_convert_list 中重复的十一项字段集合。宿舍顺序独立保留，不作为干员字段处理。这十一项覆盖编辑器的全部干员名单，包括“宿舍保留干员”。

PlanConfig.merge_config 保持唯一的配置合并实现，其唯一生产调用点为 Operators.merge_plan。共享选择组件渲染主副表控件，不复制选人和拖拽逻辑。合并后的干员名单不含空字符串。

## 验证

定向存储测试覆盖全部字段的读取、保存和导入导出。现有候补、心情上下限和干员编辑测试覆盖相邻字段。
