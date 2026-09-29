---
title: MuMu Pro 已核验实例选择
status: implemented
category: feature
date: 2026-09-30
---

# MuMu Pro 已核验实例选择

[English](2026-09-30-mumu-pro-instance-selection.md) | [中文](2026-09-30-mumu-pro-instance-selection.zh.md)

## 契约

- **[INV-DEV-11] MuMu Pro 已核验实例选择**：只读 `mumutool info all` 发现列出各个实例。选择时保存序号及实例文件路径的 Topology Fingerprint。预检和恢复重新查询所选序号，核验指纹，只使用其当前 ADB 端口。
- 管理工具输出无效、序号、路径或端口重复，以及实例文件路径变化时，在访问 ADB 前失败。已停止的实例须手动启动。不执行管理工具的启动或关闭命令。
- 用户仍可不带指纹而手动填写明确的 ADB serial；[手动绑定](../bug-fix/2026-09-30-mumu-pro-manual-binding.zh.md)规定此模式较弱的身份保证。
- 设置界面显示实例名称、序号、状态和当前 serial；重复错误只显示一次，并准确描述只读发现及手动启停。

## 实现

`MuMuProController` 限制官方查询时长与输出大小，并验证 JSON 字段。`DiscoveryService` 将观察结果交给现有实例选择器并核验已保存绑定。`DeviceSession` 避免管理工具的生命周期操作。设置界面复用实例选择并去重报错文本。

## 验证

离线测试覆盖多实例、输出无效或歧义、路径变化、端口刷新、手动回退、HTTP 草稿保留及界面提示。在本机 macOS 测试中发现实例 0 和 1；实例 0 的预检取得 1920×1080 画面并通过。实例 1 使用自己的 ADB 端口，报告未安装游戏包。[设备契约](../../../../docs/subsystems/device-control.md)规定长期行为。
