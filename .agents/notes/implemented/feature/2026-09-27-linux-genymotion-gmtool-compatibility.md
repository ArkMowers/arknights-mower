---
title: Linux Genymotion GMTool Compatibility Preset
status: implemented
category: feature
date: 2026-09-27
---

# Linux Genymotion GMTool Compatibility Preset

[English](2026-09-27-linux-genymotion-gmtool-compatibility.md) | [中文](2026-09-27-linux-genymotion-gmtool-compatibility.zh.md)

## 1. Context & Motivation
Genymotion Desktop on Linux provides the official `gmtool` CLI. To support Genymotion VMs on Linux hosts, `linux.genymotion` integrates a structured compatibility layer following official runbook specifications.

---

## 2. Invariants & Guarantees

- **[INV-01] Strict Protocol Version**: Adapter strictly validates **GMTool 3.9.0**. Unverified versions fallback to manual configuration guidance.
- **[INV-02] UUID Identity Binding**: Instance discovery and persistence bind strictly to the 36-char Machine UUID; VM labels are presentation-only.
- **[INV-03] Controlled Lifecycle**: Launch requires explicit user authorization (`POST /device/genymotion/start`); standard process exit preserves VM execution.
- **[INV-04] Isolated Endpoint Refresh**: Queries target endpoint via `admin details <uuid>`, prohibiting target replacement via foreign VM discovery.

---

## 3. Protocol Contracts & Observations

| Command | Validation Rules |
| :--- | :--- |
| `gmtool version` | Strictly checks `Version: 3.9.0` |
| `gmtool --format json admin list` | Parses `instances` array (`uuid`, `name`, `state`, `adb_serial`) |
| `gmtool admin details <uuid>` | Resolves state and allocated `ADB Serial` for bound instance |

---

## 4. Verification

- Unit tests: `device_genymotion_tests.py`, `device_genymotion_io_tests.py`, `device_genymotion_route_tests.py`.
- Tested branches: JSON list parsing, UUID validation, stopped state handling, start authorization.
