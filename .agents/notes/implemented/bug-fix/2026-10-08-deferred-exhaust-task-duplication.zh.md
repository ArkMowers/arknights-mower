---
title: 延期用尽下班任务重复生成
status: implemented
category: bug-fix
date: 2026-10-08
---

# 延期用尽下班任务重复生成

## 范围

本记录保存基线 `87b9d3aa` 上可复现的问题，以及基于 `31709700` 的修复。相关契约为[编码标准](../../../../CODING_STANDARDS.md)中的 [INV-SCHED-04]、[INV-SCHED-05]、[INV-SCHED-10] 和 [INV-SCHED-38]。

## 证据

10 月 8 日的运行日志反复生成歌蕾蒂娅的用尽下班任务，报告已有未完成的下班任务，再将新的具体安排延期至下一次跑单之后。`11:03:58` 的日志记录队列中有 45 个 SHIFT_OFF 任务。[日志摘录](../../../../arknights_mower/tests/fixtures/deferred_exhaust_20261008.json)保存来源文件名、行号和队列数量，不包含完整的 45 项任务队列，也不包含传输或账号日志。

最小离线场景包含一名心情耗尽的干员、一个工作设施、一间宿舍和一个未来的 RUN_ORDER。三轮规划与执行使具体下班任务从一份增加到四份，四份任务均停留在同一个延期时间。

## 原因

[`run_order_solver`](../../../../arknights_mower/solvers/base_schedule.py)仅按干员姓名查找 EXHAUST_OFF。`overtake_room` 将到期的用尽任务转换为具体的 SHIFT_OFF 安排，`infra_main` 随后移除已消费的用尽任务。实际驻员与投影驻员保持分离，延期使实际缓存中的干员仍然在岗。下一轮规划因此忽略已排队的具体下班任务，再次生成用尽任务。

[`_schedule_run_orders`](../../../../arknights_mower/utils/scheduler_task.py)只把下一个 RUN_ORDER 之前的任务切片交给 `_merge_deferred_dorm_schedules`。此前已排到跑单之后的副本不在该切片中。单个 SHIFT_OFF 的宿舍安排也触发合并日志，因此这条日志不能证明队列已完成去重。

## 修正契约

[INV-SCHED-38] 用尽下班任务的生成与执行识别整个队列中的一份完整 SHIFT_OFF 安排，包括已延期的未来任务。所有需要恢复的工作成员均明确安排进宿舍，或保留实际休息位置。配置宿舍成员、workaholic 和多组绑定的共享主力沿用现有用尽组完成判断的排除规则。安排回工作设施或被移出当前床位的成员不满足覆盖条件。

不完整组和独立组仍允许生成用尽下班任务。SHIFT_ON、明确的副表驻员任务、菲亚梅塔充能、专用任务补偿及强制心情上限离宿不作为下班恢复安排。具体任务消费或取消后重新允许生成。覆盖检查保留实际驻员、工作设施安排、任务身份及跑单时间，不修改延期批次合并。

`_has_pending_exhausted_shift` 直接从现有任务计划判断覆盖范围；任务生成不增加独立的恢复标记，也不修改实际驻员。

既有的具体重复任务保留在队列中，通过正常执行消化。本修复阻止新增副本，消费多余的动态用尽任务时不再添加具体安排；不同存量任务可能承担不同驻员或补偿责任，因此不追溯合并。

## 验证

[离线复现测试](../../../../arknights_mower/tests/scheduler_incident_20261008_tests.py)联动真实的生成器、用尽任务执行入口及调度器。`test_postponed_exhausted_shift_is_not_generated_again` 在修复前复现四份任务，预期为一份。保留未来 EXHAUST_OFF 标记的对照场景在修复前通过；该标记用于验证原因，不代表正式实现。

[待执行恢复测试](../../../../arknights_mower/tests/deferred_exhaust_dedup_tests.py)验证完整组与不完整组、保留或覆盖休息位置、独立干员、无关任务类型、共享成员排除、取消及多余动态任务执行。

修复后二十四个待执行恢复用例和两个事故用尽下班用例全部通过。已有用尽替班、副表休息排班和工作计时测试通过 156 项。Ruff 检查、格式检查和仓库治理检查通过。事故用例调用真实的生产入口，但模拟设备操作及休息安排构造；它们没有重放完整的存量队列，也不验证实际游戏执行。领域概念名称、含义及实际驻员与投影驻员的边界保持不变。

```text
python -m pytest arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'exhausted' -q
python -m pytest arknights_mower/tests/deferred_exhaust_dedup_tests.py -q
```

[组内床位接管记录](2026-10-08-group-bed-preemption-oscillation.zh.md)保存重复任务准入修复后，仍可能产生相反安排的独立恢复中断问题。
