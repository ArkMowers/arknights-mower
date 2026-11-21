---
title: MuMu 原生返回键分派与输入传输归因
status: implemented
category: bug-fix
date: 2026-09-28
---

# MuMu 原生返回键分派与输入传输归因

[English](2026-09-28-mumu-native-back-dispatch.md) | [中文](2026-09-28-mumu-native-back-dispatch.zh.md)

## 契约

- **[INV-DEV-01] 原生返回键分派**：选中的触控后端为 MuMu IPC 时，Android BACK 通过本会话拥有的 MuMu IPC 工作进程发送；发送结果不明确时停止会话，不重复输入，也不回退到 ADB。
- 其他 Android 按键码继续通过 ADB 发送。失败诊断独立记录实际输入传输和选中的触控后端。
- `[INV-03]` 保证失败时保留模拟器实例绑定；`[INV-04]` 保证 MuMu IPC 截图与触控保持成对选择。

## 实现

`Device.send_keyevent(4)` 根据配置的触控后端选择传输，并通过 `Device._input_once` 调用现有 `MuMuInputSession.back()`。恢复期间控制辅助对象暂时不存在不会改变传输选择；操作等待会话锁释放后使用恢复完成的辅助对象。原生辅助方法将 Android BACK 映射到 MuMu 按键 `1`，按下和抬起均使用现有的有界工作进程。任一原生事件失败都终止输入发送，不重复动作。

`TouchFailure` 保留选中的后端元数据，并接收实际输入传输信息用于诊断。ADB 失败明确标注 ADB，并提示用户检查 ADB 连接，不建议更改无关的触控后端。

笔记校验器同时接受核心不变式标识（`[INV-01]`）和子系统标识（`[INV-DEV-01]`），与文档规定的不变式登记契约一致。

[实现前简化审计](../simplification/2026-09-28-reuse-mumu-back-dispatch.zh.md) 确定复用现有原生入口。[设备子系统契约](../../../../docs/subsystems/device-control.md) 保存长期有效的分派和失败规则。

## 验证

离线测试覆盖 MuMu BACK 分派、恢复期间控制辅助对象暂时不存在时仍选择原生传输、原生按键映射、按下和抬起失败、会话终止、不通过 ADB 重复输入、其他按键保留 ADB 分派，以及实际传输错误归因。定向测试文件为 `device_touch_tests.py`、`device_mumu_input_tests.py` 和 `verify_governance_tests.py`。
