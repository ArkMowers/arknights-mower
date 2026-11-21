---
title: MuMu Pro Manual Binding Repair
status: implemented
category: bug-fix
date: 2026-09-30
---

# MuMu Pro Manual Binding Repair

[English](2026-09-30-mumu-pro-manual-binding.md) | [中文](2026-09-30-mumu-pro-manual-binding.zh.md)

## Contract

- **[INV-DEV-10] MuMu Pro Manual Binding**: Without a selected instance fingerprint, the `macos.mumu_pro` Device Profile uses its saved ADB serial in standard preflight. Missing or mismatched targets fail without adopting another device. Manager start or stop commands remain unavailable.
- A read-only check ignores saved installation and manager paths because those paths do not establish ADB identity.
- The device settings interface exposes `last_serial` and directs a profile with a serial to preflight. Verification does not persist a draft until the user saves it.
- In manual multi-instance use, the ADB serial is the connection key. The instance index is not verified, and another instance that later reuses the same serial cannot be distinguished by this gate. [Verified instance selection](../feature/2026-09-30-mumu-pro-instance-selection.md) provides a separate binding.

## Root Cause and Implementation

The compatibility preset rejected every preflight and session observation before ADB validation. The settings interface hid `last_serial` and sent a profile without a manager path to the unavailable discovery route. Preflight and session now use the shared exact-serial gate. The idle stop path declines unverified manual targets and delegates verified selections to single-instance control. The [simplification audit](../simplification/2026-09-30-reuse-manual-adb-gate.md) records the reused boundaries.

## Verification

Offline tests cover saved and draft serials, missing targets, unrelated online devices, session readiness, HTTP persistence, settings routing, and the idle stop guard. The [device contract](../../../../docs/subsystems/device-control.md) owns the permanent rule.
