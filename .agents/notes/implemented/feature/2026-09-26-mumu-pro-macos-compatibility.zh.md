---
title: macOS MuMu Pro 兼容性记录与证据矩阵
status: implemented
category: feature
date: 2026-09-26
---

# macOS MuMu Pro 兼容性记录与证据矩阵

[English](2026-09-26-mumu-pro-macos-compatibility.md) | [中文](2026-09-26-mumu-pro-macos-compatibility.zh.md)

## 1. 背景与动机
MuMu Pro 是 NetEase 面向 macOS 平台的 Android 模拟器。由于官方管理工具 `mumutool info` 输出字段与状态码缺乏公开的稳定规范，mower 将 `macos.mumu_pro` 列为兼容性记录环境，提供引导式手动配置入口，在获得确凿官方契约证据前不贸然实现未经核验的自动发现。

---

## 2. 不变式与保证

- **[INV-01] 拒绝不可信端点**：在官方 `mumutool info` 契约未确认前，禁止从旧端点、猜测端口或外部在线 ADB 设备伪造已验证状态。
- **[INV-02] 引导高级手动配置**：自动发现流程返回明确指引并提供“进入高级手动配置”入口，将用户引导至 `manual.other` 进行显式 Serial / Host:Port 配置。
- **[INV-03] 统一预检约束**：手动配置连接后仍须通过统一只读预检（Android 启动完成、1920×1080 实际帧、游戏包检查）。

---

## 3. 证据矩阵模板

| 项目 | 记录内容 |
| :--- | :--- |
| **检查日期与环境** | 日期、macOS 版本（如 macOS 14.5）、CPU 架构（Apple Silicon / Intel） |
| **MuMu Pro 版本** | 产品版本号、构建号、`mumutool` 版本 |
| **脱敏输出** | `mumutool info all` 与 `mumutool info <index>` 针对停止/运行实例的原始输出 |
| **ADB 与画面** | 使用的 ADB 版本、`sys.boot_completed`、逻辑尺寸与实际首帧尺寸 |
| **结论** | 是否满足自动发现接入条件 |

---

## 4. 验证

- 单元测试：`device_mumu_pro_tests.py`、`device_mumu_pro_route_tests.py`
- 覆盖项：自动发现返回手动指引、切换配置清理旧端点、预检拦截与放行。
