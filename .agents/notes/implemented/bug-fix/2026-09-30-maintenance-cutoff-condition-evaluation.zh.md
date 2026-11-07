---
title: Maintenance Cutoff and Condition Evaluation
status: implemented
category: bug-fix
date: 2026-09-30
---

# Maintenance Cutoff and Condition Evaluation

[English](2026-09-30-maintenance-cutoff-condition-evaluation.md) | [中文](2026-09-30-maintenance-cutoff-condition-evaluation.zh.md)

## 契约

[基建排班契约](../../../../docs/subsystems/base-scheduler.md)拥有 **[INV-SCHED-11] 维护副表执行顺序**。维护条件从公告停服开始时变为不成立，包括公告仍被缓存的情况。停服大更新停止任务线程；重新启动任务后的首次副表检查退出保存的维护副表。

## 实现

`Operators.major_maintenance_remaining_hours`在维护开始后返回无穷大，保留已保存的有限`<= hours`比较式。`next_major_maintenance_check`仅提供未来阈值唤醒。停服期间不执行公告结束检查或退出换班。

`BaseSchedulerSolver.backup_plan_solver`在首轮收敛复用初次条件结果，仅在切表改变内存状态后再次求值。维护进入检查使用同一份初次结果；后续轮次保留执行顺序及回滚检查。排班未改变时不再重复求值，不新增求值器或缓存。

## 验证

离线测试覆盖开始前一微秒、准确开始时刻、停服期间缓存公告及重新启动后退出。现有初始心情测试断言仅对原驻员和新读心情求值一次。副表收敛、订单产物及调度测试覆盖相邻行为。
