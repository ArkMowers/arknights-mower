---
title: Share Device Detection Startup
status: implemented
category: simplification
date: 2026-09-29
---

# Share Device Detection Startup

[English](2026-09-29-share-detection-start.md) | [中文](2026-09-29-share-detection-start.zh.md)

## Contract

The device settings component uses one startup request selector for bound managers and the existing AVD, redroid and Genymotion launch interfaces. Detection first reads the target state and starts only a confirmed stopped target. The read-only test remains separately available.

## Evidence

`DeviceSettings` shares request, busy-state and error handling through `startBound`. The startup selector reuses the product-specific payload validators. `DeviceControl._launch_and_verify` remains the shared backend recovery budget; MuMu Pro uses the existing session start and stop calls.
