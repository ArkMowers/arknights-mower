---
title: 原生截图进程所有权
status: implemented
category: simplification
date: 2026-09-29
---

# 原生截图进程所有权

[English](2026-09-29-native-capture-owner.md)

`MuMuCaptureSession` 为 `Device.capture_frame` 中的单个运行时调用方管理超时、取消、共享内存和进程清理。LD 截图在运行时和预检中需要相同保证。`NativeCaptureSession` 提取现有生命周期供两个厂商适配器使用，避免复制同步和清理逻辑。厂商工作进程各自保留 DLL 契约，现有 `ScreenshotSession` 继续负责重试，不增加第二套恢复策略。

[LD 截图契约](../feature/2026-09-29-ld-capture.zh.md)定义新适配器。现有 MuMu 工作进程测试和 LD 离线测试验证共享生命周期。
