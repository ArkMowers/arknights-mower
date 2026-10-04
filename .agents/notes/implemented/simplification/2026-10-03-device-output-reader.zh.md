---
title: 统一捕获输出流的所有权
status: implemented
category: simplification
date: 2026-10-03
---

# 统一捕获输出流的所有权

[English](2026-10-03-device-output-reader.md) | [中文](2026-10-03-device-output-reader.zh.md)

## 契约

[设备控制契约](../../../../docs/subsystems/device-control.md)定义 [INV-DEV-20]。每个捕获通道拥有一个临时写句柄和一个独立打开的读句柄。输出收集只改变读句柄的位置。两个句柄均由命令现有的 `ExitStack` 关闭。

## 调用方证据

`run_command` 分别创建 stdout 和 stderr 的捕获流。两处均调用同一个流对辅助函数，由该函数封装临时文件创建、独立读句柄创建和 Windows 删除共享。`run_manager_command` 保留合并输出适配器和上限。各通道共用平台句柄策略。

## 验证

[审查修复决策](../bug-fix/2026-10-03-command-output-review-repairs.zh.md)记录继承写句柄的回归测试和定向验证。实现不增加线程、重试、配置字段或外部依赖。
