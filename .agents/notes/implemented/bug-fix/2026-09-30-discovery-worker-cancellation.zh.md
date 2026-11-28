---
title: 发现工作线程取消上下文
status: implemented
category: bug-fix
date: 2026-09-30
---

# 发现工作线程取消上下文

## 契约

[INV-DEV-15] Settings Cancellation Isolation 覆盖并行提供方发现。每个提交的提供方收到调用方上下文的独立副本。设置操作中的截图辅助进程等待忽略已停止任务的信号，仍响应进程退出和设备关闭取消，不改变共享事件。

## 边界与简化

共享 `_concurrent` 提交边界为每个操作分别复制上下文，并通过副本的 `run` 执行操作。macOS 和 Linux 提供方发现共用此边界，不新增厂商专用取消分支或额外包装。提供方上下文变更保持局部，结果顺序保持稳定，`MowerExit` 到达现有 HTTP 取消边界。

[设置取消决策](../../implemented/bug-fix/2026-09-30-device-settings-cancellation.zh.md)定义请求作用域和 HTTP 结果。

## 验证

离线测试使用真实 `DiscoveryService`、`BlueStacksAirDiscovery` 和线程池，仅模拟设备 I/O。覆盖任务停止后成功执行 Air 截图、截图中退出或关闭设备、HTTP 返回 `device_operation_cancelled`、配置和停止信号保持不变、调用方策略恢复，以及同时执行的提供方使用独立上下文副本。
