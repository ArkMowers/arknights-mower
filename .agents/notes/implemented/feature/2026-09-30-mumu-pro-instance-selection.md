---
title: MuMu Pro Verified Instance Selection
status: implemented
category: feature
date: 2026-09-30
---

# MuMu Pro Verified Instance Selection

[English](2026-09-30-mumu-pro-instance-selection.md) | [中文](2026-09-30-mumu-pro-instance-selection.zh.md)

## Contract

- **[INV-DEV-11] MuMu Pro Verified Selection**: Read-only `mumutool info all` discovery offers each distinct instance. A selection saves its index and a Topology Fingerprint of the VM path. Preflight and recovery query the selected index again, verify that fingerprint, and use only its current ADB port.
- Malformed manager output, duplicate indices, paths or ports, and changed VM paths fail before ADB access. A stopped instance requires a manual launch. No manager start or stop command is issued.
- A user may still enter an explicit ADB serial without a fingerprint; [manual binding](../bug-fix/2026-09-30-mumu-pro-manual-binding.md) defines that mode's weaker identity guarantee.
- The settings view shows instance name, index, state and current serial. It presents a repeated error once and describes read-only discovery and manual lifecycle accurately.

## Implementation

`MuMuProController` bounds the official query and validates its JSON fields. `DiscoveryService` maps observations into the existing instance selector and checks saved bindings. `DeviceSession` avoids manager lifecycle actions. The settings view reuses discovery selection and deduplicates the error message.

## Verification

Offline tests cover multiple instances, malformed or ambiguous output, changed paths, port refresh, manual fallback, HTTP draft preservation and UI messages. On the tested macOS host, instances 0 and 1 were both discovered; instance 0 passed preflight with a 1920×1080 frame. Instance 1 reached its own ADB port and reported the game package missing. The [device contract](../../../../docs/subsystems/device-control.md) owns the permanent rule.
