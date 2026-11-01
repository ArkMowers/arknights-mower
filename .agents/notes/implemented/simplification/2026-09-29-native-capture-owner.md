---
title: Native Capture Process Ownership
status: implemented
category: simplification
date: 2026-09-29
---

# Native Capture Process Ownership

[中文](2026-09-29-native-capture-owner.zh.md)

`MuMuCaptureSession` owns timeout, cancellation, shared memory and process cleanup for its single runtime caller in `Device.capture_frame`. LD capture needs the same guarantees in runtime and preflight. `NativeCaptureSession` extracts this existing lifecycle for both vendor adapters and avoids duplicating its synchronization and cleanup code. Vendor workers retain their own DLL contracts; the existing `ScreenshotSession` retains retry ownership. No second recovery policy is introduced.

The [LD capture contract](../feature/2026-09-29-ld-capture.md) defines the new adapter. Existing MuMu worker tests and LD offline tests verify the shared lifecycle.
