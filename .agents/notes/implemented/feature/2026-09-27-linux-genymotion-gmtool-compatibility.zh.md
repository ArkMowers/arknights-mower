---
title: Linux Genymotion GMTool 兼容性预设
status: implemented
category: feature
date: 2026-09-27
---

# Linux Genymotion GMTool 兼容性预设

[English](2026-09-27-linux-genymotion-gmtool-compatibility.md) | [中文](2026-09-27-linux-genymotion-gmtool-compatibility.zh.md)

## 1. 背景与动机
Genymotion Desktop 在 Linux 上提供官方 `gmtool` 命令行工具。为了支持在 Linux 宿主机上运行 Genymotion 虚拟机，`linux.genymotion` 预设接入了基于官方规范的兼容性记录层。

---

## 2. 不变式与保证

- **[INV-01] 严格契约版本**：初始协议适配器限定支持 **GMTool 3.9.0**。其他未核验输出格式的版本提示使用手动配置，避免解析未知格式产生误判。
- **[INV-02] UUID 绑定**：发现与绑定保存 VM 的 UUID（36位标准 UUID 格式），VM 名称仅作为展示文本。
- **[INV-03] 启动受控与存活保留**：启动需经用户在前端显式确认（`POST /device/genymotion/start`）；普通退出 mower 保持 VM 运行，不自动关闭或重启。
- **[INV-04] 端点单独刷新**：新会话通过 `admin details <uuid>` 仅查询当前绑定的 VM，禁止通过枚举其他 VM 替代失效目标。

---

## 3. 协议契约与观察指标

| 命令 | 校验要点 |
| :--- | :--- |
| `gmtool version` | 严格校验 `Version: 3.9.0` |
| `gmtool --format json admin list` | 解析 `instances` 列表中的 `uuid`、`name`、`state` 与 `adb_serial` |
| `gmtool admin details <uuid>` | 解析单实例就绪状态与当前分配的 `ADB Serial` |

---

## 4. 验证与现场矩阵

- 单元测试：`device_genymotion_tests.py`、`device_genymotion_io_tests.py`、`device_genymotion_route_tests.py`
- 覆盖项：JSON 列表解析、UUID 格式校验、停止状态端点处理、启动确认路由。
- 现场验收状态：Linux 物理机真实环境验收未运行（Unverified on hardware）。
