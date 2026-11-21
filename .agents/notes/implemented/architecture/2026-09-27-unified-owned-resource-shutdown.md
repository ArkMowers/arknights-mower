---
title: Unified Owned Resource Shutdown & Process Lifecycle
status: implemented
category: architecture
date: 2026-09-27
---

# Unified Owned Resource Shutdown & Process Lifecycle

[English](2026-09-27-unified-owned-resource-shutdown.md) | [中文](2026-09-27-unified-owned-resource-shutdown.zh.md)

## 1. Context & Motivation
In complex automation applications, heterogeneous termination paths (tray exit, window close, SIGINT/Ctrl+C, startup aborts, fatal device errors) risk leaking background helpers (DroidCast, MaaTouch, scrcpy, MuMu IPC workers), stale port forwards, and unmanaged screen resolution overrides.

This design establishes a centralized process-level shutdown coordinator with a three-phase reverse resource teardown contract.

---

## 2. Invariants & Guarantees

- **[INV-01] Unified Exit Routing**: All termination triggers (tray, UI, signal, device crash) route unconditionally to a single `ShutdownCoordinator`.
- **[INV-02] Monotonic Gate Closure**: Entering shutdown permanently closes admission gates, rejecting new start, recovery, or reconnection requests.
- **[INV-03] Strict Teardown Order**:
  1. Deactivate scheduler, broadcast stop signal, cancel pending tasks;
  2. Interrupt blocking device I/O (sockets, IPC, pipes);
  3. Bounded wait for worker thread join (10s budget);
  4. Compensate physical device screen resolution;
  5. Terminate owned helper subprocesses and ADB forward mappings;
  6. Flush screenshot queues (5s budget);
  7. Terminate HTTP server, child UI processes, and logging pipes.
- **[INV-04] Strict Ownership Verification**: Cleanup operations verify owner PID and resource tokens, never terminating external emulators, foreign forwards, or shared ADB daemons.
- **[INV-05] Fault-Tolerant Continuation**: Individual resource cleanup failures log structured diagnostics but never block subsequent resource disposals.

---

## 3. Technical Design

### 3.1 I/O Interruption vs Resource Disposal
- **Interrupt Phase (`interrupt`)**: Sets `_interrupted` event to unblock threads waiting on socket recv, HTTP, or IPC pipes.
- **Close Phase (`close`)**: Safely disposes process handles, issues remote stop commands, and unbinds owned forward mappings after worker thread yield.

### 3.2 MuMu IPC Native Worker Isolation
Native DLL calls (`nemu_input`, `nemu_connect`) are isolated in a dedicated worker subprocess communicated via IPC pipes. Subprocess timeouts allow hard termination signals from the main process, preventing process hangs.

---

## 4. Verification & Field Matrix

### 4.1 Automated Tests
- Application, desktop, screenshot, and worker teardown: 128 tests (`application_shutdown_tests`, `device_shutdown_tests`).
- Device, helper, and I/O cleanup: 190 tests passed (`device_owned_resources_tests`, `device_droidcast_tests`).
- ADB timeout and recovery budget propagation: 17 tests passed.

### 4.2 Windows Field Matrix (2026-09-27)

| Scenario | Method | Verdict | Notes |
| :--- | :--- | :--- | :--- |
| **Native Tray Exit** | Desktop app + pystray callback | Blocked | `GetCursorPos` raises WinError 5 on Windows 11 |
| **Ctrl+C Signal** | Dedicated console `CTRL_C_EVENT` | Passed | Clean exit with code 0 in 11.58s without forced kill |
| **Orphan Process Audit** | Process snapshot check | Passed | No dangling Python/UI/Helper worker processes |
| **External Emulator Protection** | Observed MuMu 12 instance | Passed | External VM instances preserved |
