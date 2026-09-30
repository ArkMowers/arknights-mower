---
title: MuMu Pro 管理器准备取消
status: implemented
category: bug-fix
date: 2026-09-30
---

# MuMu Pro 管理器准备取消

## 契约

[INV-DEV-15] Settings Cancellation Isolation 覆盖 MuMu Pro 管理器准备。进程退出或设备关闭在命令、轮询和完成边界取消准备。发现取消后不执行后续管理器命令，HTTP 返回 `device_operation_cancelled` 而非成功。已停止任务的信号保持不变，不取消设置页准备。

## 边界与简化

`MuMuProController.prepare_manager` 复用现有作用域内的 `csleep` 检查取消，并用于默认轮询等待。`DeviceControl.prepare_mumu_pro_manager` 在发布成功前再次检查该策略。准备保留单一单调时钟截止时间、一次应用打开尝试及现有命令超时；执行中的命令受其超时约束。不新增取消回调、厂商策略或重试包装。实例启动、关闭和共享 ADB 行为保持不变。

[设置取消决策](../../implemented/bug-fix/2026-09-30-device-settings-cancellation.zh.md)定义请求作用域和 HTTP 边界。

## 验证

离线测试使用真实 `DeviceControl`、`DeviceSession`、`ProductionSimulator` 和 `MuMuProController`，模拟进程 I/O。退出和关闭覆盖 `port`、应用打开、实例清单查询、轮询和完成边界，覆盖直接调用及两个设置 HTTP 路由，任务停止信号分别设置和未设置。测试验证配置和任务信号保持不变、取消策略恢复及任务停止后准备成功。Air 测试夹具登记规范化应用路径，与临时目录存在符号链接别名时的生产发现行为一致。
