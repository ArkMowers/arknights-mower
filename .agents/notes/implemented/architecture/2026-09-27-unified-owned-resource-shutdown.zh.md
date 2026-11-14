---
title: 统一自有资源关闭与进程生命周期
status: implemented
category: architecture
date: 2026-09-27
---

# 统一自有资源关闭与进程生命周期

[English](2026-09-27-unified-owned-resource-shutdown.md) | [中文](2026-09-27-unified-owned-resource-shutdown.zh.md)

## 1. 背景与动机
在复杂桌面与自动化应用中，托盘菜单退出、窗口关闭、Ctrl+C 中断、启动失败及运行时致命错误容易走散乱的退出路径，导致后台 helper 进程（DroidCast、MaaTouch、scrcpy、MuMu IPC Worker）残留、ADB 端口转发泄露、以及实体设备修改的屏幕分辨率未能及时恢复。

本设计统一了进程级生命周期管理器，确立了三阶段逆序资源释放契约。

---

## 2. 不变式与保证

- **[INV-01] 统一关闭入口**：所有退出原因（托盘退出、窗口关闭、Ctrl+C、启动失败、致命设备异常）均路由至同一个进程级 `Shutdown` 协调器。
- **[INV-02] 门禁单向关闭**：一旦进入退出流程，设备与应用门禁立即永久关闭，拒绝任何后续启动、恢复或重连请求。
- **[INV-03] 严格关闭顺序**：
  1. 停用调度器，发出全局停止信号并取消排队任务；
  2. 中断阻塞的设备 I/O（Socket / IPC / 管道）；
  3. 有限等待 Worker 线程退出（上限 10s）；
  4. 补偿并恢复实体设备分辨率；
  5. 关闭自有 Helper 子进程与 ADB Forward 映射；
  6. 刷新并关闭截图队列与后台存储（上限 5s）；
  7. 停止 HTTP 服务、销毁 UI 子进程、注销日志转发与管道句柄。
- **[INV-04] 所有权严格限定**：资源清理前必须核验创建进程 PID 与资源标识，绝不操作非当前 mower 进程创建的外部模拟器、Forward 映射或全局 ADB Server。
- **[INV-05] 容错继续**：单项资源清理失败时记录异常，但严禁阻断后续其他资源的释放流程。

---

## 3. 技术设计

### 3.1 设备 I/O 中断与最终释放解耦
- **中断阶段 (`interrupt`)**：设置 `_interrupted` 事件，唤醒并中断阻塞在 Socket 接收、HTTP 请求或 IPC 管道上的线程，使其退出循环。
- **释放阶段 (`close`)**：在 Worker 线程交出控制权后，安全关闭进程句柄、向远端发送退出命令、移除精确匹配的 ADB Forward 端口映射。

### 3.2 MuMu IPC 输入子进程隔离
MuMu 原生 DLL 的 `nemu_input` / `nemu_connect` / `nemu_disconnect` 属于可能产生原生死锁的阻塞调用。将 Native 调用隔离至专属子进程中，主进程通过 Pipe 发送事件。当子进程阻塞超时时，主进程可通过进程信号终止子进程，确保主程序能如期退出。

---

## 4. 验证与现场矩阵

### 4.1 自动化测试覆盖
- **应用、桌面、截图及 Worker 退出接缝**：128 项测试（`application_shutdown_tests`, `device_shutdown_tests`, `desktop_lifecycle_tests` 等）。
- **设备、Helper 和 I/O 清理**：190 项全部通过（`device_owned_resources_tests`, `device_droidcast_tests`, `device_scrcpy_tests` 等）。
- **ADB 超时与 Budget 传播**：17 项全部通过。

### 4.2 Windows 现场验收结果（2026-09-27）

| 场景 | 测试手段 | 结果 | 限制说明 |
| :--- | :--- | :--- | :--- |
| **原生托盘退出** | 真实桌面程序 + pystray 回调 | Blocked | Windows 11 下 pystray 执行 `GetCursorPos` 触发 WinError 5 权限错误，托盘菜单退出未通过 |
| **Ctrl+C 信号退出** | 独立 console 发送 `CTRL_C_EVENT` | Passed | 主进程正常以状态码 0 退出，耗时 11.58s，未发生强制 kill |
| **残留进程核验** | 进程快照检查 | Passed | 现场工具链子进程全部清理，未遗留 Python/UI/Helper 僵尸进程 |
| **模拟器退出保护** | 观察 MuMu 12 实例 | Passed | 正常退出未误关用户的外部模拟器实例 |
