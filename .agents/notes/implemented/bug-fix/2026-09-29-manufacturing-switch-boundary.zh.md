---
title: 无人机加速后的制造产物切换边界
status: implemented
category: bug-fix
date: 2026-09-29
---

# 无人机加速后的制造产物切换边界

[English](2026-09-29-manufacturing-switch-boundary.md) | [中文](2026-09-29-manufacturing-switch-boundary.zh.md)

## 契约

- **[INV-SCHED-06] 制造产物切换边界**：无人机加速后，制造产物切换跟踪被加速的当前这一份何时完成；下一份的倒计时不能推迟本次切换。
- 确认操作等待被加速的这一份预计剩余时间，并采用巡检时与当前生产力中的较小值以及配置的缓冲时间。没有加速结果的切换沿用最新倒计时复核。

## 证据与实现

2026-09-27 21:29，`yunxi` 日志显示 B301 使用 55 架无人机，计划等待 0 秒，随后却将产物切换推迟 5,426 秒。该时长接近当前生产力下一份中级作战记录的完整生产时间。另有五次延期呈现相同模式。原有复核用加速前保存的队列边界减去已进入下一份的倒计时。

`BaseSchedulerSolver._execute_manufacture_acceleration` 在确认加速后记录当前这一份剩余的基础时间。`_change_manufacture_product` 使用该数值和已流逝的生产时间，不再使用过期的队列边界。[基建调度契约](../../../../docs/subsystems/base-scheduler.md) 保存长期有效的规则。

## 验证

离线测试覆盖立即跨过当前份边界、页面跳转时跨过边界，以及当前份仍需等待的情形。制造产物切换定向测试覆盖周边行为。
