---
title: DroidCast 降级后的按住截图
status: implemented
category: bug-fix
date: 2026-10-10
---

# DroidCast 降级后的按住截图

## 契约与复杂度评估

修复保持 [INV-DEV-07]、[INV-DEV-17] 和 [INV-DEV-24]。按住期间的 Capture Frame 沿用会话当前生效后端，只取帧一次，不执行恢复、就绪状态变更或输入重放。截图失败且独立输入辅助连接不可用时，恢复完整辅助资源；仅修复输入不算截图重建。

`Device.screencap(recover=False)` 绕过 `ScreenshotSession.degraded`，在普通截图已经降级到 ADB 后仍调用所选 DroidCast 辅助进程。`DeviceControl.capture` 还将任何恢复动作视为截图重建，包括仅修复输入。修复将后端选择留在应用边界，复用现有截图、辅助资源清理和 Recovery Budget 机制，不增加队列、工作线程、第二套降级策略或不变量编号。Capture Frame、Instance Binding 和 Recovery Budget 的现有术语含义保持不变。

yunxi 日志在按住选人截图反复报告映射缺失前，记录了空闲模拟器重启和 ADB 重连，但没有记录移除原有转发的操作。映射诊断记录期望映射及该本地端口的有界观测；降级仅在发生转换时记录一次原因。

## 验证

离线回归覆盖降级后的普通截图与按住选人截图、同轮截图和输入连接失败、取消、无效帧、触控释放及其他映射保留。参见[设备契约](../../../../docs/subsystems/device-control.md)与[按住截图决策](../../implemented/simplification/2026-10-09-held-swipe-capture.zh.md)。

`DeviceResult.helpers_rebuilt` 区分已完成的完整辅助资源重建与仅修复输入。截图故障在修复输入后，仍执行本次允许的截图重建。`capture_once()` 使用应用锁，但不清理延迟释放资源；外层输入操作在抬手后完成清理。

两项事件回归在修复前失败。定向 DroidCast、按住截图、截图后端、触控和设备会话测试共 458 项通过；治理测试 27 项通过；五个修改的 Python 文件均通过 Ruff 和格式检查。结构治理通过，保留已归档自有 ADB 决策引用缺失测试文件的两项历史警告。检查使用离线替身，不构成实机复现，也不确定最初移除转发的操作。

## Standards Findings

通过：复用已有不变量编号，保留 Instance Binding、其他转发、持久化 Device Profile 和输入 Recovery Budget。当前生效截图路径不增加线程、队列或并行恢复策略。现有术语含义保持不变，无需且未修改术语表。

## Spec Findings

通过：降级后的按住截图返回同一设备的 ADB 画面，不调用 DroidCast 或恢复。同轮截图和输入故障修复两类资源，不把仅修复输入计为截图重建。无效帧和截图错误保留结构化报告；取消和延迟清理在关闭所属资源前完成抬手。
