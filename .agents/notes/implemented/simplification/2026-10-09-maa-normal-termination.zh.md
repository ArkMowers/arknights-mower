---
title: MAA 长任务正常结束
status: implemented
category: simplification
date: 2026-10-09
---

# MAA 长任务正常结束

[English](2026-10-09-maa-normal-termination.md)

**[INV-MAA-07] 长任务正常结束**：肉鸽、保全派驻和生息演算正常完成或被调度器中断时，不得仅因 `running()` 返回 false 而报告错误；核心错误回调和调用异常保留错误报告。

`BaseSchedulerSolver.maa_plan_solver` 包含唯一的 `maa_crash` 标志及长任务通用中断报错。停止运行的状态不包含失败原因，正常完成后也返回该状态。删除标志和报错分支减少五行代码，同时消除重复的 ERROR 通知；该通知会再次记录相同错误，并可能发送邮件。没有调用方或外部接口使用此标志。

[MAA 集成契约](../../../../docs/subsystems/maa-integration.md) 定义结束报告。回调翻译保留完成、停止和核心错误消息。调用异常保留既有错误通知。场景重置、任务截止时间、停止请求、主题恢复和空闲交接维持既有行为。

`maa_error_no_exit_tests.py` 覆盖任务立即完成时不报错、不重试、不关闭游戏，并保留调用失败通知。`maa_scene_handoff_tests.py` 覆盖运行中的任务自行结束或被调度停止，验证场景状态刷新且不追加错误。回调测试验证核心错误级别。

## Standards Findings

通过：删除局部崩溃推断，复用回调报告，不增加状态、包装或配置。领域定义和资源生命周期保持不变。

## Spec Findings

通过：长任务正常结束不产生通用错误或 ERROR 通知；实际回调错误和调用异常保留错误报告。
