---
title: Rescue Facility Capacity and Dorm Batching
status: archived
category: bug-fix
date: 2026-10-04
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# 救急设施容量与宿舍合并安排

## 契约

[INV-SCHED-09] 使用配置中的贸易站、制造站完整岗位数作为设施等级，局部替班也不以待替换人数代替等级。一级到三级的订单上限为 6/8/10，制造站容量为 24/36/54。精一孑组合使用对应等级的订单上限，条件式上限扣减不再作为固定容量惩罚。等级未知或未实测精零积单量时，不假定孑的额外收益。多萝西按同站实际生效的莱茵科技技能数量计分，包括自身。干员额外容量转化不包含设施基础仓库容量。

[INV-SCHED-03] 在需要恢复的主班仍等待工作替班时暂停普通补床；已离岗主班仍按共享优先级分床。同轮宿舍计划并入待执行救急换班，不覆盖已预约床位，持久化记录与合并计划一致。合并后的操作预算与强制清退冲突时延后补床。既有执行顺序保持工作站在前、宿舍在后。

## 简化

既有评分函数接收设施等级，不增加等级扫描。既有换班任务承载同轮宿舍安排，不为这些安排新增宿舍任务。[排班契约](../../../../docs/subsystems/base-scheduler.md) 定义这些规则。

## 依据

[游戏基建数据](https://github.com/Kengxxiao/ArknightsGameData/blob/master/zh_CN/gamedata/excel/building_data.json) 提供各等级容量和岗位数。[孑的技能](https://prts.wiki/w/孑) 区分积单效果与精一组合。仓库内生效技能描述提供多萝西和容量转化规则。

## 审查

Standards Findings：无未解决问题。复用既有选人、共享恢复层级和任务归属。合并安排保留预约并重新检查强制清退预算；不新增设备观测或持久化结构。

Spec Findings：无未解决问题。定向离线测试通过 1213 项及 20 个子测试，覆盖一至三级贸易容量、局部替班、莱茵科技双人组合、主班先于普通补位、计划合并和操作窗口不足。
