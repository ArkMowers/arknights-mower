---
title: Idle Recovery Boundary
status: implemented
category: simplification
date: 2026-10-07
---

# Idle Recovery Boundary

## 契约

空闲唤醒时的设备故障离开 MAA 任务异常边界，交回既有 Device Control 恢复入口。待执行调度任务与输入结果不明时的派发暂停保持不变。

## 简化审查

`maa_plan_solver` 的一次正常空闲收尾位于 MAA 异常处理范围内，重复承担外层调度器的设备故障处理职责。将调用移到 MAA 异常处理之后，移除重复的异常路由，不增加恢复包装、重试策略或异常分类器。实际初始化、任务下发与 MAA 执行故障保留原通知。

## 验证

离线测试在设备就绪恢复成功后返回原始设备缺失异常。空闲故障向外传播且不发送 MAA 通知；实际 MAA 故障保留通知。已分类设备错误与停止信号保留既有行为。
