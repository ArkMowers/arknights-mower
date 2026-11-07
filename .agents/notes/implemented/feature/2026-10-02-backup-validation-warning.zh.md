---
title: Incomplete Backup Validation Permits Startup
status: implemented
category: feature
date: 2026-10-02
---

# Incomplete Backup Validation Permits Startup

[English](2026-10-02-backup-validation-warning.md) | [中文](2026-10-02-backup-validation-warning.zh.md)

## 契约

预算耗尽返回 `status: incomplete` 与 `success: false`，不声明全面校验通过。手动校验显示警告；启动记录该警告并继续。干员持有及主表错误、已确认的合并排班冲突和意外分析异常仍阻止启动。运行时合并排班检查与收敛保护继续生效。

## 实现

专用预算异常区分允许继续的覆盖未完成与其他错误。现有 success/message 调用方保留布尔语义；识别状态的启动及界面调用方单独处理未完成。已知设施产物相等条件按房间共享符号状态，包含未列出值。未知条件保持保守。[排班契约](../../../../docs/subsystems/base-scheduler.md)与[覆盖决策](../../implemented/bug-fix/2026-10-02-backup-validation-coverage.zh.md)定义配置校验范围。

## 简化审计

一种异常类型标识两处预算出口；调用方不解析翻译后的错误字符串，也不重复条件分析。没有持久化跳过校验选项或第二套校验器。

## 验证

离线测试覆盖两类预算警告、阻止启动的主表及持有错误、意外异常、警告后的真实调度启动入口、预检未完成后的运行时拒绝，以及不同产物条件互斥。

## 规范审查

通过。现有术语及配置结构保持原状。测试隔离设备及网络操作。分析预算、截止时间上限与调用方状态保留符合既有契约。

## 功能审查

通过。定向回归验证调用方行为及边界情况。运行时配置检查保留既有错误处理。
