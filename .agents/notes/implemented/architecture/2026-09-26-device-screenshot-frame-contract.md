---
title: Device Screenshot Validation & Frame Contract
status: implemented
category: architecture
date: 2026-09-26
---

# Device Screenshot Validation & Frame Contract

[English](2026-09-26-device-screenshot-frame-contract.md) | [中文](2026-09-26-device-screenshot-frame-contract.zh.md)

## 1. Context & Motivation
Simulators and devices at various lifecycle stages (booting, loading screens, orientation changes) return frames with varying resolutions incompatible with CV template matching. Stretching or padding frames inside device control layers causes recognition hallucinations.

This contract establishes a unified strict validation standard for capture frames, defining boundaries and single-rebuild limits across backends.

---

## 2. Invariants & Guarantees

- **[INV-01] Strict Frame Dimensions**: Preflight and runtime accept only `uint8` RGB capture frames with shape strictly equal to `(1080, 1920, 3)`. Scaling, padding, or rotating portrait frames inside the device layer is prohibited.
- **[INV-02] Blank Frame Validity**: Solid black frames conforming to structural dimensions are valid; pixel darkness does not signify transport failure (cold boot transitions naturally exhibit transient black frames).
- **[INV-03] Single Rebuild Limit**: On capture failure, the session may execute at most one resource rebuild for the selected backend; persistent failure raises a session error without unbounded retries or emulator restarts.
- **[INV-04] Failures Preserve Configuration**: Persistent capture failures report structured failure codes and candidate backends without mutating persistent user settings.

---

## 3. Backend Implementation Contracts

### 3.1 ADB gzip
- Queries target Android SDK version, distinguishing 12-byte headers (Android <= 8.0) from 16-byte headers (Android >= 8.1).
- Validates gzip checksums and uncompressed byte lengths, rejecting truncated or trailing-padded streams.

### 3.2 MuMu 12 Native IPC
- Preserves native return codes and buffer dimensions (`1920x1080` RGBA).
- **Display Binding**: Binds IPC directly to instance Display 0 rather than resolving via game package name, preventing binding failures before game window initialization.
- **Process Isolation**: Native DLL invocations run in a dedicated worker process with a 10s monotonic frame deadline.

### 3.3 DroidCast 1.3.0
- Establishes local HTTP listener and verifies requests with a 16 MiB single-image ceiling.

---

## 4. Verification

- Automated test suites: `screenshot_adb_tests.py`, `device_screenshot_backend_tests.py`, `device_mumu_frame_tests.py`.
- Tested branches: Corrupted headers, dimensional non-conformance, native IPC negative error codes, valid solid-black frame handling.
