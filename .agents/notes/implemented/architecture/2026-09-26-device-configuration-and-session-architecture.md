---
title: Device Configuration Compatibility & Session Architecture
status: implemented
category: architecture
date: 2026-09-26
---

# Device Configuration Compatibility & Session Architecture

[English](2026-09-26-device-configuration-and-session-architecture.md) | [中文](2026-09-26-device-configuration-and-session-architecture.zh.md)

## 1. Context & Motivation
Prior to refactoring, simulator and device configuration fields were scattered across `Conf` (`Conf.adb`, `Conf.simulator`, `Conf.mumu12IPC`, `Conf.droidcast`, `Conf.touch_method`). Runtime connection state and persisted configuration were tightly coupled, causing stale endpoint reuse upon switching presets, cross-talk between multi-instances, and lack of bounded recovery policies during device errors.

This architecture encapsulates device configuration into a clean, persisted data model `Conf.device` (`DeviceProfile`), providing strong-contract single-instance bounded recovery and read-only preflight mechanisms at runtime.

---

## 2. Invariants & Guarantees

- **[INV-01] Transient vs Persisted Isolation**: `DeviceProfile` stores only explicit user selections (`preset_id`, `installation_path`, `manager_path`, `config_path`, `adb_path`, `instance_id`, `instance_name`, `instance_uuid`, `topology_fingerprint`, `last_serial`, `game_package`, `screenshot_backend`, `touch_backend`, `recovery_timeout`, `recovery_attempts`, `recovery_local_wait`). Unpersisted discovery scans and transient socket sessions remain in memory and are never persisted.
- **[INV-02] Target Rebinding Clears Endpoints**: Changing preset, installation directory, manager path, configuration path, or instance identifier must immediately clear `last_serial` to prevent stale endpoint reuse.
- **[INV-03] Failure Preserves Target Identity**: Discovery, preflight, or recovery failure must never silently alter persistent configuration, switch backends, or automatically fallback to another online device on the host.
- **[INV-04] IPC Pair Cohesion**: MuMu IPC screenshot backend and touch backend must be selected together; neither may be used without the other.
- **[INV-05] Shared ADB Guard**: Socket-level protocol negotiation must verify shared ADB server state before running CLI operations; implicit `kill-server` invocations are strictly prohibited.

---

## 3. Configuration & Migration Model

### 3.1 HTTP Endpoints & Layering
- `GET /conf`: Returns full configuration, including on-the-fly migration of legacy fields into `device`. Pure read operation without writing to disk.
- `PATCH /conf`: Recursively validates and merges incoming fields. Arrays and free-key maps are completely replaced. Validation failures return HTTP 400; save errors return HTTP 500 while preserving existing settings.
- `POST /conf`: Backward-compatible legacy form submissions. Explicit new `device` payload takes precedence over legacy fields.

### 3.2 Backward Compatibility Mapping
When saving, `DeviceProfile` automatically generates legacy compatibility fields:
- `simulator.name`, `simulator.simulator_folder`, `simulator.index`
- `maa_adb_path`, `adb`, `package_type`
- `mumu12IPC`, `droidcast.enable`, `custom_screenshot.enable`, `touch_method`

---

## 4. Vendor Discovery & Endpoint Resolution

### 4.1 Windows MuMu 12
- **Discovery Sources**: Registry HKLM/HKCU uninstall entries, standard paths, user-defined paths, and running processes.
- **Manager Constraints**: Executes `MuMuManager.exe info -v all`, 3s command timeout, 6s total budget, 1 MiB output ceiling, 64 instances max.
- **Endpoint Resolution**: Selected instance queries `info -v <bound index>`, verifying ADB state, Android boot completion, 1920x1080 canvas frame, and game package.

### 4.2 Windows LDPlayer 9
- **Discovery Sources**: LDPlayer 9 uninstall registry, running processes, custom paths.
- **Manager Constraints**: Executes `ldconsole.exe list2` or `dnconsole.exe list2`.
- **Endpoint Verification**: Obtains process PID via `list2`, cross-referencing Windows TCP listening ports and `boot_id` from `ldconsole adb --index <bound index> --command "shell cat /proc/sys/kernel/random/boot_id"`.

### 4.3 Windows Nox
- **Discovery Sources**: Uninstall registry, standard paths, process list, `NoxConsole.exe list`.
- **Identity Binding**: Reads Machine UUID and NAT rules from `<VM name>.vbox`, generating `topology_fingerprint` via SHA-256 over VM names.
- **Endpoint Verification**: Cross-references `boot_id` via `NoxConsole adb -name:<current title>` and selected ADB.

### 4.4 Windows BlueStacks 5
- **Discovery Sources**: `SOFTWARE/BlueStacks_nxt` registry (`InstallDir`, `UserDefinedDir`).
- **Config Parsing**: Reads `bluestacks.conf`, parsing `bst.instance.<key>.status.adb_port` or `adb_port`.
- **Endpoint Verification**: Verifies 16-hex Android ID via `settings --user 0 get secure android_id`.

### 4.5 macOS BlueStacks Air
- **Discovery Sources**: `/Applications/BlueStacks.app` or `~/Applications/BlueStacks.app`.
- **Endpoint Rules**: Candidate endpoint `127.0.0.1:5555`, prompts user to enable ADB in emulator settings.

### 4.6 macOS & Linux Android Virtual Device (AVD)
- **Discovery Sources**: Android SDK path, `ANDROID_SDK_ROOT`, `ANDROID_HOME`, `emulator -list-avds`.
- **Lifecycle**: Starts `emulator -avd <name>` only upon explicit `POST /device/avd/start`; shuts down only if the instance was launched by the current process.

### 4.7 Physical Device Temporary Preparation (`manual.physical`)
- **Authorization**: Single-run authorization (`POST /start/0` with `preparation_serial`), unpersisted.
- **Preparation Flow**: Acquires exclusive lock, records original physical/override geometry, executes `wm size 1920x1080` (or `1080x1920`), verifies canvas frame and touch viewport.
- **Compensation**: Executes `wm size reset` or restores original override unconditionally upon normal completion, error, or process exit.

---

## 5. Session Readiness & Recovery Policy

### 5.1 Readiness Verdicts
`DeviceControl.readiness()` classifies status into: `absent`, `offline`, `booting`, `ready`.
- `ready` criteria: Selected transport in `device` state, `sys.boot_completed == 1`, and decoded initial frame strictly matches `(1080, 1920, 3)`.

### 5.2 Recovery Policy Parameters (`RecoveryPolicy`)
- `attempts`: Maximum reconnection retries (default 3, user-configurable).
- `timeout`: Total recovery deadline budget (default 180s, user-configurable).
- `local_wait`: Post-boot stabilization wait (default 10s, user-configurable).
- `poll_interval`: Polling interval (default 1s).
- `shutdown_wait`: Termination confirmation timeout (default 30s).

---

## 6. Verification & Matrix

| Module | Verification Method | Coverage |
| :--- | :--- | :--- |
| Config Migration & Partial Save | Unit tests (`device_config_tests.py`) | Array replace, field omission, backward mapping |
| Windows Simulator Discovery | Offline fixtures (`fixtures/mumu12_*.json`, `nox_*.txt`, `ldplayer9_*.txt`) | Normal, multi-instance, stopped, malformed, timeout |
| Session Recovery & Budget | Injection tests (`device_session_tests.py`, `device_session_io_tests.py`) | Offline recovery, reconnect, frame wait, budget exhaustion |
| Physical Preparation & Compensation | Lifecycle tests (`device_preparation_lifecycle_tests.py`) | Normal recovery, abort compensation, lock contention |
