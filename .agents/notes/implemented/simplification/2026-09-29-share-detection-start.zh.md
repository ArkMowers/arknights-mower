---
title: 共用设备检测启动流程
status: implemented
category: simplification
date: 2026-09-29
---

# 共用设备检测启动流程

[English](2026-09-29-share-detection-start.md) | [中文](2026-09-29-share-detection-start.zh.md)

## 契约

设备设置组件使用一个启动请求选择器，调用已绑定管理器及现有 AVD、redroid、Genymotion 启动接口。检测先读取目标状态，仅启动已确认停止的目标；只读测试仍可单独使用。

## 证据

`DeviceSettings` 通过 `startBound` 共用请求、忙碌状态和错误处理。启动选择器复用各产品的请求验证函数。`DeviceControl._launch_and_verify` 继续负责共用恢复预算；MuMu Pro 使用现有会话启动和停止接口。
