---
title: DroidCast 1.3.0 截图生命周期与端口转发管理
status: implemented
category: feature
date: 2026-09-27
---

# DroidCast 1.3.0 截图生命周期与端口转发管理

[English](2026-09-27-droidcast-capture-lifecycle.md) | [中文](2026-09-27-droidcast-capture-lifecycle.zh.md)

## 1. 背景与动机
DroidCast 能够通过 HTTP 快速输出 Android 屏幕帧，但过去存在 helper 进程失控残留、ADB forward 端口未受保护、签名冲突时缺乏清晰指导等问题。

本设计升级至 DroidCast 1.3.0 (versionCode 146)，引入了严格的 helper 命名隔离、所有权确认与安全的生命周期管理。

---

## 2. 不变式与保证

- **[INV-01] 版本强一致**：启动前校验 `dumpsys package`，必须为 `1.3.0` / `versionCode 146`。旧版使用 `install -r` 覆盖；设备存在更新版本时不自动降级。
- **[INV-02] 签名冲突不自动卸载**：当遇到签名不匹配（`INSTALL_FAILED_UPDATE_INCOMPATIBLE`）时，系统严禁自动执行 `uninstall` 清除应用数据，必须返回明确指引提示用户手动确认处理。
- **[INV-03] 专属 Forward 映射**：每个会话生成独立随机标识 `mower-droidcast-<uuid>`，使用 `forward --no-rebind` 建立映射。清理时仅移除 serial、本地端口与远端端口均匹配的自有映射。
- **[INV-04] 所有权与超时传播**：Forward 映射建立成功后立即记录所有权，即使后续 ADB 检查发生超时也能在失败分支中正确触发清理。

---

## 3. 技术参数与预算

- **超时预算**：ADB 命令超时 10s，APK 安装超时 60s，Helper 首帧启动超时 10s，HTTP 连接超时 2s，读取超时 3s。
- **网络与安全**：HTTP 请求关闭环境代理（`trust_env = False`），不跟随重定向，单张图像上限 16 MiB。
- **旋转支持**：支持按配置执行 180° 图像翻转（`cv2.ROTATE_180`）。

---

## 4. 现场验收矩阵 (2026-09-27)

| 条件 | 现场实测值 | 状态 |
| :--- | :--- | :--- |
| **测试宿主** | Windows 11 10.0.26200 | Passed |
| **模拟器** | MuMu 12 (6.8.1.0), Android 12 / API 32, ADB 36.0.0 | Passed |
| **覆盖升级耗时** | 1.2.1 -> 1.3.0 覆盖安装 + 首帧耗时 3.78s | Passed |
| **重建耗时** | 连续三次重建首帧耗时 1.50s ~ 1.67s，关闭后 `forward` 与远端进程均清空 | Passed |
| **首次安装验收** | 纯净设备全新安装 | Blocked（依赖 Mock 测试） |
