---
title: Reuse Manual ADB Gate for MuMu Pro
status: implemented
category: simplification
date: 2026-09-30
---

# Reuse Manual ADB Gate for MuMu Pro

[English](2026-09-30-reuse-manual-adb-gate.md) | [中文](2026-09-30-reuse-manual-adb-gate.zh.md)

## Contract

`PreflightService` already validates an exact ADB serial, Android readiness, the game package, and the canvas frame. `DeviceSession` already uses `last_serial` when the instance state is unknown. Manual MuMu Pro binding needs no separate endpoint resolver or connection fallback.

## Evidence

For a manually entered serial, `ProductionSimulator` returns an unknown instance observation and the shared ADB gate verifies that exact target. A separate read-only manager query supports [verified instance selection](../feature/2026-09-30-mumu-pro-instance-selection.md). Removing the preflight and session hard refusals reuses the existing read-only gate; the legacy stop entry requires one explicit guard against an unverified manager command.

The [device contract](../../../../docs/subsystems/device-control.md) owns the resulting binding rule.
