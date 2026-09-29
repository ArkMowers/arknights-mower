---
title: Device Settings Save Scope and Start-and-Test Action
status: implemented
category: feature
date: 2026-09-28
---

# Device Settings Save Scope and Start-and-Test Action

[English](2026-09-28-device-settings-save-scope-and-start-and-test.md) | [中文](2026-09-28-device-settings-save-scope-and-start-and-test.zh.md)

## Contract

- Settings that never change which device mower targets — capture backend, touch backend, recovery budget, manager query timeout, simulator boss key and its delay — persist as soon as the user edits them. `[INV-01]`
- Device identity — preset, installation path, manager path, product configuration path, instance identity, endpoint, game server — persists only through a verified connection. `[INV-01]`, `[INV-02]`
- An immediate save submits only the keys that one edit changed. Identity edits pending in the same draft never reach the persisted profile. `[INV-02]`
- The device profile owns the simulator boss key and its delay. A profile that never stored the field adopts the legacy value once, then the legacy `simulator.hotkey` and `simulator.hotkey_delay` keys carry a copy for older readers and never write back, so a cleared boss key stays cleared.
- `POST /device/start` launches the bound instance through its preset's own multi-instance manager and verifies the connection inside the session's single monotonic budget. It never selects another instance on the host. `[INV-03]`, `[INV-04]`
- Only presets that own a multi-instance manager accept the request; every other preset reports `start_unsupported` and keeps the manual launch.
- The device settings test button carries `测试连接` (read-only) as its default action and `启动并测试连接` (start, then test) as its dropdown twin. The read-only test stays the default.
- The device connection copy states verification in plain words; the abbreviated term 预检 no longer appears in user-visible device connection text.
- The capture and touch backends stay outside the advanced identity form: they never change which device mower targets, so the settings page exposes them without opening it. The recovery budget, the timeouts and the boss key stay with the identity fields under the advanced toggle.
- The read-only rule and the save rule sit in the help of the connection status tag. The notice above the buttons carries preset-specific guidance only.
- The session reports one user-visible line per connection state change — the selected device, the instance launch, the ADB connect and the successful connection. Attempt counters, budgets and every observation stay in the debug log.
- A stopped instance and the launch that follows it read as one line, and the session reports a verified connection once, after the display gate. `[INV-03]`
- Both ways into the game are logged: `Device.launch()` prints `明日方舟，启动！` when the probe confirmed the process was force-stopped, and the foreground restore prints `游戏不在前台，正在把游戏调到前台...` when the probe can only treat an unconfirmable process as running. No silent path into the game remains.

## Implementation

`Conf.sync_legacy_device_fields` writes the profile's boss key and delay into the legacy simulator keys and performs no reverse copy. `profile_from_legacy` still migrates an old configuration when no device profile is stored, and `Conf.updated` merges an explicitly submitted legacy form field before the sync runs, so older callers keep working.

`DeviceControl.start_bound` resolves the ADB executable, binds the profile to the session, calls `DeviceSession.ensure_ready` — which launches a stopped instance through `ProductionSimulator.start` — and runs `PreflightService.check` on the verified endpoint. `MANAGED_INSTANCE_PRESETS` names the presets whose own manager can launch an already bound instance. The action persists nothing.

The UI splits the two save scopes in `DeviceSettings.vue:edit()`: `isImmediateDeviceField` marks the non-identity keys, and `editedDevicePatch` returns only the keys one edit changed, including a coupled capture/touch backend. The patch is diffed against the same draft it is applied to, so identity edits pending in that draft cancel out. `deviceSettingsState` returns `fields` (identity and repair) separately from `connectionFields` (capture and touch backends), and `connectionVisible` keeps the second group on the page while the identity form stays closed. `DeviceSettings.vue` keeps that group below the buttons without a divider title; the capture backend, the touch backend and the rotate/command row that follows the capture backend share one grid, so their row pitch matches — in two adjacent grids the rotate row sat closer to the row above it. The tuning knobs stay behind the 超时保护与高级控制 divider. The section widens its label column to 158px with an important override of the settings form's inline 120px: at 120px a label plus its help icon wraps onto a second line and every row grows taller. Field labels wrap inside the label column instead of painting under the input, and the capture and touch labels use the glossary terms `截图后端` / `触控后端`.

`DeviceSession` keeps the flow line apart from the diagnostics: `_format_human_observation` renders one sentence per observation, `_flow_names_state` marks the two states the flow names itself (a ready verdict, and a stopped instance whose launch follows), and `recovery.py` and `_action` log their attempt counters at debug level. `window.py` reports the boss key after the keystroke was sent. `DropDown.vue` no longer pins its menu to the trigger width, so a long option label is not shifted out of the menu box. The flow lines read `使用设备：…` for the chosen target and `连接成功：…` for the verdict.

## Verification

Focused offline suites cover the new start action (stopped instance launched once, running instance not relaunched, unsupported preset rejected, active session rejected, closing session rejected, missing adapter rejected, unknown payload keys rejected), the boss key ownership (a cleared key stays cleared, a legacy key still migrates into a profile block that predates the field, an explicit delay beats the legacy value), the boss key trigger after a successful instance start, the connection flow log lines (a stopped instance and its launch on one line, one ADB connect line without attempt counters, the ready verdict reported once), and the frontend save scope, connection group placement and dropdown options. The suites are `device_start_bound_tests.py`, `device_config_tests.py`, `device_window_tests.py`, `device_session_tests.py`, `device_recovery_tests.py`, `device_droidcast_start_tests.py`, `device_preflight_io_tests.py`, and `ui/src/utils/deviceSettings.test.js`. The menu geometry of `DropDown.vue` was confirmed in a headless Chromium render of the component with the device settings options. The [device subsystem contract](../../../../docs/subsystems/device-control.md) owns the permanent start action, its preset gate and the connection log contract.
