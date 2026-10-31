---
title: Linux Waydroid Session Discovery & D-Bus Binding
status: implemented
category: feature
date: 2026-09-27
---

# Linux Waydroid Session Discovery & D-Bus Binding

[English](2026-09-27-linux-waydroid-session-discovery.md) | [中文](2026-09-27-linux-waydroid-session-discovery.zh.md)

## 1. Context & Motivation
Waydroid runs containerized Android on Linux via LXC. Its CLI lacks multi-instance selection, and session execution status is split between CLI commands and system D-Bus services.

`linux.waydroid` correlates `waydroid status` with D-Bus `GetSession` to establish immutable user/data directory bindings.

---

## 2. Invariants & Guarantees

- **[INV-01] Cross-Validated Session Identity**: Correlates Session/Container status from `waydroid status` with `user_id` and `waydroid_data` from D-Bus `id.waydro.ContainerManager.GetSession`.
- **[INV-02] Non-Interactive D-Bus Execution**: Calls `busctl` with `--system --json=short --auto-start=no --allow-interactive-authorization=no` to block unsolicited daemon spawns or auth prompts.
- **[INV-03] Explicit Diagnostic Gating**: Uninitialized states (`Waydroid is not initialized`) or `FROZEN` containers return actionable error codes without automatic mutation.
- **[INV-04] Strict DHCP IP Binding**: Extracts ADB endpoints strictly from official status IP reports appending `:5555`, prohibiting target inference from foreign devices.

---

## 3. Status Handling Table

| Official Status | Mower Verdict | Action |
| :--- | :--- | :--- |
| Missing `waydroid` | `missing_installation` | Guide user to configure path |
| Uninitialized | `waydroid_uninitialized` | Guide terminal initialization |
| `Session: STOPPED` | `stopped` | Prompt start in preflight, preserve binding |
| `Session/Container: RUNNING` | `running` | Resolve IP:5555 and run preflight |
| `Container: FROZEN` | `waydroid_container_not_running` | Guide unfreezing container |

---

## 4. Verification

- Unit tests: `device_waydroid_tests.py`, `device_waydroid_io_tests.py`, `device_waydroid_route_tests.py`.
- Tested branches: Single IP resolution, multi-IP conflict gating, D-Bus schema variations across systemd v240-v256.
