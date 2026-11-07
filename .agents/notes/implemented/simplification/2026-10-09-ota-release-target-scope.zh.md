---
title: OTA release target scope
status: implemented
category: simplification
date: 2026-10-09
---

# OTA 发布目标范围

[INV-UPD-05] Release Artifact Scope 从后续发行构建中排除 macOS x64，仅为 Windows x64 和 Android ARM64 生成 OTA，包含 Nightly。Android 运行时路径保留规范的相对 POSIX 名称，包括 Debian 多架构文件名中的冒号，并拒绝路径穿越、驱动器前缀、重复条目和宿主数据文件。无效目标包在渠道索引更新前终止发布。

发行工作流移除 Intel macOS 矩阵项，保留 Linux 完整包和 macOS ARM64。MowerRelease 分开声明完整包和 OTA 目标，每完成一个差分即上传，并记录下载和构建耗时，GitHub 命令具有有限超时。Nightly 对两个支持平台使用同一个 OTA 发布器。Android 重建器接受与发布器一致的运行时路径。

本次简化从发行路径中移除 Linux 差分生成，不增加替代的归档抽象。定向工作流测试覆盖保留的构建矩阵。MowerRelease 与 Android 仓库测试覆盖运行时路径兼容、安全拒绝和增量发布恢复。

[软件更新契约](../../../../docs/subsystems/software-update.md)定义该不变量。
