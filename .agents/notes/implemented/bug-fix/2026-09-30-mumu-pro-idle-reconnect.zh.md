---
title: MuMu Pro 空闲唤醒重连
status: implemented
category: bug-fix
date: 2026-09-30
---

# MuMu Pro 空闲唤醒重连

## 契约

[INV-DEV-14] Startup Reconnect Budget 要求启动就绪期间被拒绝的 ADB 重连保留有界重试和观察，直到现有截止时间。每次重试都验证同一 Instance Binding。绑定变化、共享 ADB 错误和取消仍立即终止；禁止切换其他端点或重复重启模拟器。

## 边界与简化

MuMu Pro 的运行状态与 TCP 端口监听不代表 Android ADB 已就绪。`DeviceSession._wait_ready` 复用现有 `_action` 计数和 `_wait_local` 轮询窗口，不新增 MuMu Pro 专用恢复循环。重连被拒绝时不将 serial 标记为已成功连接。剩余动作预算允许再次重连同一目标；动作耗尽后，仅在同一截止时间内进行只读就绪轮询。

## 验证

离线测试复现空闲启动后首次重连失败，覆盖随后就绪、持续失败、绑定变化、共享 ADB 失败和取消。成功恢复保持所选实例，不改变已保存的端点。远端诊断仅使用只读日志与状态查询，不重启服务或执行模拟器生命周期操作。
