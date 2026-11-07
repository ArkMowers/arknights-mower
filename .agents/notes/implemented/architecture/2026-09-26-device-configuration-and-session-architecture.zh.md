---
title: 设备配置兼容性与会话架构
status: implemented
category: architecture
date: 2026-09-26
---

# 设备配置兼容性与会话架构

[English](2026-09-26-device-configuration-and-session-architecture.md) | [中文](2026-09-26-device-configuration-and-session-architecture.zh.md)

## 1. 背景与动机
在重构前，模拟器与设备配置散落在全局 `Conf` 的多个字段中（`Conf.adb`、`Conf.simulator`、`Conf.mumu12IPC`、`Conf.droidcast`、`Conf.touch_method` 等）。运行时状态与持久化配置高度耦合，导致换绑模拟器时残留旧端点、多实例切换时串号、以及设备异常时缺乏有界恢复策略。

本架构将设备配置抽象为稳定的持久化配置模型 `Conf.device`（`DeviceProfile`），并在运行时提供强契约的单实例有界恢复与只读预检机制。

---

## 2. 不变式与保证

- **[INV-01] 瞬态状态与持久配置隔离**：`DeviceProfile` 仅存储用户显式选择的设备配置（`preset_id`、`installation_path`、`manager_path`、`config_path`、`adb_path`、`instance_id`、`instance_name`、`instance_uuid`、`topology_fingerprint`、`last_serial`、`game_package`、`screenshot_backend`、`touch_backend`、`recovery_timeout`、`recovery_attempts`、`recovery_local_wait`）。自动发现扫描结果与内存瞬态协议握手绝不作为持久化字段存盘。
- **[INV-02] 换绑立即清空 Serial**：更改 `preset_id`、安装路径、管理器路径、产品配置文件路径或 `instance_id` 时，系统必须立即清空旧的 `last_serial`，防止旧端点被错误复用。
- **[INV-03] 失败路径保持配置与失败状态**：发现、预检或恢复失败时，不得静默修改持久化配置，不得自动切换其他后端，亦不得自动替代为同机器上的其他在线设备。
- **[INV-04] IPC 成对绑定**：MuMu IPC 截图后端与触控后端必须成对选择；选择 IPC 截图必须同时使用 IPC 触控。
- **[INV-05] 共享 ADB 守卫**：在调用 ADB CLI 执行操作前，必须通过 Socket 探测共享 ADB Server 协议版本；版本不匹配或服务异常时拒绝执行，严禁 CLI 触发隐式 `kill-server`。

---

## 3. 配置与迁移模型

### 3.1 HTTP 接口与配置分层
- `GET /conf`：返回完整配置，包含从旧配置在内存中迁移出的 `device`。纯读取不主动写盘。
- `PATCH /conf`：仅递归校验并合并传入字段。数组与自由键 Map（如 `rogue.collectible_mode_start_list`）全量替换。校验失败返回 HTTP 400；文件保存失败返回 HTTP 500 并保留原配置。
- `POST /conf`：兼容旧版全量表单提交。显式提交的新 `device` 字段优先级高于旧字段。

### 3.2 兼容性映射规则
保存配置时，`DeviceProfile` 会自动同步生成旧版本所需的兼容字段：
- `simulator.name`、`simulator.simulator_folder`、`simulator.index`
- `maa_adb_path`、`adb`、`package_type`
- `mumu12IPC`、`droidcast.enable`、`custom_screenshot.enable`、`touch_method`

---

## 4. 厂商发现与端点解析

### 4.1 Windows MuMu 12
- **发现源**：注册表 HKLM/HKCU 的卸载项、固定标准路径、用户自定义路径及当前运行进程路径。
- **管理器约束**：执行 `MuMuManager.exe info -v all`，单条命令超时 3s，总预算 6s，输出上限 1 MiB，最多保留 64 个实例。
- **端点刷新**：选定实例后通过 `info -v <bound index>` 读取当前端点，并验证 ADB 状态、Android 启动完成、1920×1080 实际帧与游戏包。

### 4.2 Windows LDPlayer 9（雷电9）
- **发现源**：雷电 9 卸载注册表、运行中进程、自定义路径。
- **管理器约束**：执行 `ldconsole.exe list2` 或 `dnconsole.exe list2`。
- **端点核验**：通过 `list2` 获取当前进程 PID，并结合 Windows TCP 监听端口和 `ldconsole adb --index <bound index> --command "shell cat /proc/sys/kernel/random/boot_id"` 交叉核验 `boot_id`。

### 4.3 Windows Nox（夜神）
- **发现源**：卸载注册表、标准路径、进程列表、`NoxConsole.exe list`。
- **身份绑定**：读取 `<VM name>.vbox` 文件中的 Machine UUID 与网络转发规则，结合 VM 名称集合的 SHA-256 生成拓扑指纹 `topology_fingerprint`。
- **端点核验**：通过 `NoxConsole adb -name:<current title>` 和选定 ADB 交叉比对 `boot_id`。

### 4.4 Windows BlueStacks 5
- **发现源**：`SOFTWARE/BlueStacks_nxt` 注册表中的 `InstallDir` 与 `UserDefinedDir`。
- **配置解析**：读取 `bluestacks.conf`，严格按选定实例的 `bst.instance.<key>.status.adb_port` 或 `adb_port` 获取端口。
- **端点核验**：通过 `settings --user 0 get secure android_id` 核验 16 位十六进制 Android ID，排除端口串用。

### 4.5 macOS BlueStacks Air
- **发现源**：`/Applications/BlueStacks.app` 或 `~/Applications/BlueStacks.app`。
- **端点规则**：候选端点 `127.0.0.1:5555`，要求用户手动在设置中开启 ADB。

### 4.6 macOS & Linux Android Virtual Device (AVD)
- **发现源**：Android SDK 路径、`ANDROID_SDK_ROOT`、`ANDROID_HOME`、`emulator -list-avds`。
- **启动与控制**：仅在用户显式触发 `POST /device/avd/start` 时启动 `emulator -avd <name>`；仅在任务结束后且属于当前进程启动的实例才允许执行关闭。

### 4.7 实体设备临时整备 (`manual.physical`)
- **授权机制**：仅允许单次运行授权（`POST /start/0` 携带 `preparation_serial`），不持久化配置。
- **整备流程**：获取设备排他锁，记录原始 `Physical` 与 `Override` 分辨率至持久化 Store，下发 `wm size 1920x1080`（或 `1080x1920`），校验实际帧与输入视口。
- **补偿与恢复**：无论任务正常结束、报错还是进程退出，均自动触发 `wm size reset` 或恢复原始 `Override`。

---

## 5. 会话就绪性与恢复策略

### 5.1 状态判定
`DeviceControl.readiness()` 返回四种状态：`absent`、`offline`、`booting`、`ready`。
- `ready` 条件：选定 transport 处于 `device` 状态、`sys.boot_completed == 1`，且解码后的首帧尺寸严格等于 `(1080, 1920, 3)`。

### 5.2 恢复策略参数 (`RecoveryPolicy`)
- `attempts`: 恢复重试最大次数（默认 3 次，支持高级设置自定义）。
- `timeout`: 恢复总时间预算（默认 180 秒，支持高级设置自定义）。
- `local_wait`: 启动后等待基础延迟（默认 10 秒，支持高级设置自定义）。
- `poll_interval`: 轮询间隔（默认 1 秒）。
- `shutdown_wait`: 模拟器关闭确认等待（默认 30 秒）。

---

## 6. 验证与矩阵

| 模块 | 验证方式 | 覆盖分支 |
| :--- | :--- | :--- |
| 配置迁移与 Partial Save | 单元测试 (`device_config_tests.py`) | 数组替换、字段剔除、向后兼容映射 |
| Windows 模拟器发现 | 离线 Fixture (`fixtures/mumu12_*.json`, `nox_*.txt`, `ldplayer9_*.txt`) | 正常、多实例、停止、格式损坏、超时 |
| 会话恢复与预算传播 | 注入式测试 (`device_session_tests.py`, `device_session_io_tests.py`) | 离线恢复、重连、帧等待、预算耗尽 |
| 实体设备整备与补偿 | 生命周期测试 (`device_preparation_lifecycle_tests.py`) | 正常恢复、异常退出补偿、锁竞争 |
