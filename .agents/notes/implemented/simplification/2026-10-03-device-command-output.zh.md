---
title: 共用设备命令输出所有权
status: implemented
category: simplification
date: 2026-10-03
---

# 共用设备命令输出所有权

[English](2026-10-03-device-command-output.md) | [中文](2026-10-03-device-command-output.zh.md)

## 契约

设备命令共用 [manager_io.py](../../../../arknights_mower/utils/device/manager_io.py) 的临时文件执行机制。[设备控制契约](../../../../docs/subsystems/device-control.md)中的 [INV-DEV-20] 定义有限命令等待与输出所有权。

## 调用证据

厂商发现与实例就绪检查原本使用 `run_manager_command`；预检、ADB 版本检查、分辨率查询和 MuMu 输入初始化在本决策之前分别走管道调用。复用管理器机制消除了这两种执行策略的差异。`run_command` 保留 stdout/stderr 分离、合并输出、二进制输出、文本解码与可选退出码检查。管理器适配器保留现有的合并二进制输出与 1 MiB 限额。一般设备命令的捕获输出合计上限为 32 MiB，包含自定义截图帧字节。

## 验证

合成可执行程序在命令之外保留继承的输出句柄。定向测试验证命令完成、超时、输出限额与自有进程清理，不访问设备或网络服务。

## 规范审查

PASS：共用执行机制保留现有管理器导入、显式输出策略、有限内存与自有资源清理。治理链接与现有领域术语保持有效。

## 规格审查

PASS：启动调用方共用文件机制，保留命令参数、输出解析与故障分类。离线夹具验证继承句柄行为与输出兼容性。
