---
title: Linux Waydroid 会话发现与 D-Bus 绑定
status: implemented
category: feature
date: 2026-09-27
---

# Linux Waydroid 会话发现与 D-Bus 绑定

[English](2026-09-27-linux-waydroid-session-discovery.md) | [中文](2026-09-27-linux-waydroid-session-discovery.zh.md)

## 1. 背景与动机
Waydroid 是 Linux 平台基于 LXC 的 Android 容器。其 CLI 工具不包含多实例选择器，且状态输出与会话数据目录分散在 CLI 与系统 D-Bus 服务中。

`linux.waydroid` 预设通过结合 `waydroid status` 与系统 D-Bus 的 `GetSession` 实现不可变用户/数据目录绑定。

---

## 2. 不变式与保证

- **[INV-01] 交叉核验会话身份**：通过 `waydroid status` 获取 Session/Container 状态与 IP 地址，同时通过 `busctl` 调用 `id.waydro.ContainerManager.GetSession` 获取 `user_id` 与 `waydroid_data` 路径，二者必须完全一致。
- **[INV-02] 零交互安全调用**：`busctl` 参数包含 `--system --json=short --auto-start=no --allow-interactive-authorization=no`，禁止自动拉起服务或弹出提权窗口。
- **[INV-03] 未初始化与冻结显式报错**：遇到 `Waydroid is not initialized` 或容器处于 `FROZEN` 状态时，返回具体诊断并提示用户在终端操作，禁止 mower 自动执行初始化或解冻。
- **[INV-04] 端点严格取自官方 DHCP**：ADB 端点仅提取自官方状态报告的 IP 并追加 `:5555`，禁止从不相关的外部在线设备推测目标。

---

## 3. 状态处理矩阵

| 官方状态 | mower 判定 | 响应动作 |
| :--- | :--- | :--- |
| 找不到 `waydroid` | `missing_installation` | 提示补充管理程序路径 |
| 未初始化 (`waydroid init`) | `waydroid_uninitialized` | 提示在终端完成初始化 |
| `Session: STOPPED` | `stopped` | 只读预检提示启动，保存绑定 |
| `Session: RUNNING` & `Container: RUNNING` | `running` | 解析 IP:5555 并进入预检 |
| `Container: FROZEN` | `waydroid_container_not_running` | 提示恢复容器运行 |

---

## 4. 验证

- 单元测试：`device_waydroid_tests.py`、`device_waydroid_io_tests.py`、`device_waydroid_route_tests.py`
- 覆盖项：单 IP 解析、多 IP 冲突需要用户选择、D-Bus 输出格式兼容性（针对 systemd v240 ~ v256）、数据目录切换失效处理。
