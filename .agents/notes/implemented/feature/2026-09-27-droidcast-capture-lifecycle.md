---
title: DroidCast 1.3.0 Capture Lifecycle & Forward Management
status: implemented
category: feature
date: 2026-09-27
---

# DroidCast 1.3.0 Capture Lifecycle & Forward Management

[English](2026-09-27-droidcast-capture-lifecycle.md) | [中文](2026-09-27-droidcast-capture-lifecycle.zh.md)

## 1. Context & Motivation
DroidCast streams Android screen frames over HTTP. Prior implementations suffered from orphaned helper processes, unguarded ADB forward collisions, and silent failures during signature mismatches.

This design upgrades to DroidCast 1.3.0 (versionCode 146), implementing strict helper isolation, ownership tracking, and guarded lifecycle management.

---

## 2. Invariants & Guarantees

- **[INV-01] Exact Version Enforcement**: Validates `dumpsys package` for `1.3.0` / `versionCode 146`. Upgrades older versions via `install -r`; newer versions are preserved without downgrading.
- **[INV-02] Signature Conflict Protection**: On `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, automatic uninstallation is strictly prohibited; actionable manual resolution guidance is returned.
- **[INV-03] Dedicated Forward Tokens**: Sessions bind forwards via `forward --no-rebind` using unique tokens (`mower-droidcast-<uuid>`). Disposal removes only exact matching serial and port pairs.
- **[INV-04] Early Ownership Registration**: Ownership is registered immediately upon forward creation, guaranteeing cleanup even if subsequent verification commands timeout.

---

## 3. Technical Parameters & Budgets

- **Deadlines**: ADB command 10s, APK install 60s, Helper init 10s, HTTP connect 2s, HTTP read 3s.
- **Network**: Disables environment proxy (`trust_env = False`), disables redirects, 16 MiB frame payload limit.
- **Orientation**: Supports optional 180-degree rotation (`cv2.ROTATE_180`).

---

## 4. Field Verification Matrix (2026-09-27)

| Condition | Field Observation | Verdict |
| :--- | :--- | :--- |
| **Host** | Windows 11 10.0.26200 | Passed |
| **Emulator** | MuMu 12 (6.8.1.0), Android 12 / API 32, ADB 36.0.0 | Passed |
| **Upgrade Latency** | 1.2.1 -> 1.3.0 install + first frame: 3.78s | Passed |
| **Rebuild Latency** | Three consecutive rebuilds: 1.50s - 1.67s; clean forward disposal | Passed |
| **Fresh Install** | Clean instance install | Blocked on hardware (mock verified) |
