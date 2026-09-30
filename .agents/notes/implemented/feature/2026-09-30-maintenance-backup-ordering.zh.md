---
title: Maintenance Backup Ordering
status: implemented
category: feature
date: 2026-09-30
---

# Maintenance Backup Ordering

[English](2026-09-30-maintenance-backup-ordering.md) | [中文](2026-09-30-maintenance-backup-ordering.zh.md)

## 契约

[基建排班契约](../../../../docs/subsystems/base-scheduler.md)拥有 **[INV-SCHED-11] 维护副表执行顺序**。[编码标准](../../../../CODING_STANDARDS.md)和[审查清单](../../../skills/mower-code-review/references/invariants-checklist.md)登记同一保证。

## 实现

维护条件使用一整行编辑原有比较式，默认提前半小时。`Operators.next_major_maintenance_check`提供阈值时刻及公告结束时刻。单个空任务唤醒正常副表收敛，不新增持久配置。

进入副表前，通过`adjust_run_order_for_maintenance`仅提前现有停服前跑单任务。任务保留无人机加速标记及失败后的重试时间；排队的原班恢复任务继承同批标记。副表切换等待该批任务全部完成，期间暂停生成新的跑单任务。

`swap_plan`记录合并后哪些主班位置来自维护副表。后续显式安排替换权限，`Current`保留权限。普通主班与替班校验仍然有效。存在获准的跑单主班时，现有跑单房间过滤及队列同步暂停全部贸易站跑单，保留其他任务，退出后恢复。

维护条件复用`HelpText`提供问号说明。已有条件保留保存的提前小时数。用户批准的词汇表补充使用排班表、动态换班及无人机加速说明维护副表，持久配置结构不变。

## 验证

离线测试覆盖全部跑单干员、嵌套条件与字符串常量、位置覆盖顺序、替班、全站暂停、其他任务保留、定时检查去重、退出检查、进入顺序、重试延期及原班恢复。现有订单产物、副表条件、救急条件及任务调度测试验证相邻行为。前端测试覆盖默认半小时和已有比较式兼容性。
