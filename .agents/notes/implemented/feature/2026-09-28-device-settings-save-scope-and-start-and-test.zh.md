---
title: Device Settings Save Scope and Start-and-Test Action
status: implemented
category: feature
date: 2026-09-28
---

# 设备设置保存范围与启动并测试连接

[English](2026-09-28-device-settings-save-scope-and-start-and-test.md) | [中文](2026-09-28-device-settings-save-scope-and-start-and-test.zh.md)

## 契约

- 不影响 mower 目标设备的设置——截图后端、触控后端、恢复预算、多开管理器查询超时、模拟器老板键及其延迟——在用户修改后立即保存。`[INV-01]`
- 设备身份——预设、安装目录、管理程序路径、产品配置路径、多开实例身份、连接地址、游戏服务器——只在连接验证通过后保存。`[INV-01]`、`[INV-02]`
- 立即保存只提交本次编辑真正改变的键；同一草稿里待检测保存的身份修改不会写入已保存配置。`[INV-02]`
- 模拟器老板键及其延迟由设备配置持有。从未保存过该字段的旧配置会先迁移一次旧值，此后旧字段 `simulator.hotkey`、`simulator.hotkey_delay` 只为旧版读取方保留副本、不再反向写入，因此清空后的老板键保持为空。
- `POST /device/start` 使用预设自带的多开管理器启动已绑定实例，并在会话的唯一单调预算内验证连接，不会改选主机上的其他实例。`[INV-03]`、`[INV-04]`
- 只有自带多开管理器的预设接受该请求；其他预设返回 `start_unsupported`，仍由用户手动启动。
- 设备设置的测试按钮默认执行 `测试连接`（只读），并在下拉中提供 `启动并测试连接`（先启动再测试）。只读测试仍是默认动作。
- 设备连接相关文案用平实说法描述验证过程；面向用户的设备连接文案不再使用简称“预检”。
- 截图后端与触控后端不改变 mower 的目标设备，因此不随“高级设置”折叠：设置页无需展开高级设置即可更换它们。超时、重试、关停上限、状态检测与老板键属于调参，仍随“高级设置”折叠。
- 只读规则与保存规则写在连接状态标签的说明里；按钮上方的提示只保留预设自身的注意事项。
- 会话为每次连接状态变化只报告一行用户可见日志：所选设备、启动实例、连接 ADB、连接成功。动作计数、预算与每次观察只写入调试日志。
- 停止的实例与随后的启动读作一行；连接验证通过后只报告一次“连接成功”。`[INV-03]`
- 进入游戏的两个动作都有日志：探针确认进程已停止（force-stop）时由 `Device.launch()` 打印“明日方舟，启动！”；探针无法确认停止、只能按“运行中”处理时打印“游戏不在前台，正在把游戏调到前台...”。进入游戏不再有静默路径。

## 实现

`Conf.sync_legacy_device_fields` 把设备配置中的老板键与延迟写入旧字段，不再反向复制。未保存设备配置时，`profile_from_legacy` 仍从旧配置迁移；旧版表单显式提交的字段由 `Conf.updated` 在同步之前合并，旧调用方不受影响。

`DeviceControl.start_bound` 解析 ADB 程序、把配置绑定到会话、调用 `DeviceSession.ensure_ready`（其中通过 `ProductionSimulator.start` 启动已停止的实例），再对验证后的连接地址执行 `PreflightService.check`。`MANAGED_INSTANCE_PRESETS` 列出自带多开管理器、可以启动已绑定实例的预设。该动作不持久化任何内容。

前端在 `DeviceSettings.vue:edit()` 上区分两种保存范围：`isImmediateDeviceField` 标记非身份字段，`editedDevicePatch` 只返回本次编辑改变的键（包含成对的截图/触控后端）。差异以同一份草稿为基准，因此草稿里待检测保存的身份修改不会被带出去。`deviceSettingsState` 把设备身份与修复字段（`fields`）和截图、触控后端（`connectionFields`）分开返回，`connectionVisible` 在身份表单折叠时仍保留第二组。`DeviceSettings.vue` 让该组不带分隔标题、常显在按钮下方，截图后端、触控后端与随截图后端出现的旋转截图/截图命令同处一个网格，行距因此一致；调参收拢在“超时保护与高级控制”分隔线之后。本节的标签列加宽到 158px（`!important` 覆盖设置表单的内联 120px），否则标签连同 help 图标会被拆到两行，每行配置都会长高一行。字段标签在设置表单固定标签列内换行，不再被输入框覆盖。截图与触控字段的标签使用术语表用词“截图后端”“触控后端”。

`DeviceSession` 把流程行与诊断分开：`_format_human_observation` 为每次观察渲染一句话，`_flow_names_state` 标出由流程自己命名的两种状态（就绪结论，以及紧随其后的启动），`recovery.py` 与 `_action` 的动作计数只写调试日志。`window.py` 在按键发出之后才报告老板键。`DropDown.vue` 不再把菜单宽度钉在触发按钮上，较长的选项文案不会再被挤出菜单框。流程行为 `使用设备：…`（所选目标）与 `连接成功：…`（验证结论）。

## 验证

离线聚焦测试覆盖新的启动动作（已停止实例只启动一次、运行中实例不再启动、不支持的预设被拒绝、会话运行中被拒绝、会话关闭中被拒绝、缺少适配器被拒绝、未知请求键被拒绝）、老板键归属（清空后保持为空、早于该字段的旧配置块仍能迁移旧值、显式默认延迟优先于旧值）、实例启动成功后触发老板键、连接流程日志（停止的实例与启动同一行、ADB 连接只有一行且不带尝试计数、就绪结论只报告一次），以及前端保存范围、连接分组位置与下拉选项。相关测试为 `device_start_bound_tests.py`、`device_config_tests.py`、`device_window_tests.py`、`device_session_tests.py`、`device_recovery_tests.py`、`device_droidcast_start_tests.py`、`device_preflight_io_tests.py` 与 `ui/src/utils/deviceSettings.test.js`。`DropDown.vue` 的菜单几何在无头 Chromium 中按设备设置的选项实际渲染确认。永久契约由[设备子系统说明](../../../../docs/subsystems/device-control.md)持有：启动动作、预设门槛与连接日志契约。
