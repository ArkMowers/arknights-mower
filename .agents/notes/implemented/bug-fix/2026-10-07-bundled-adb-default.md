---
title: Bundled ADB Default
status: implemented
category: bug-fix
date: 2026-10-07
---

# Bundled ADB Default

## Contract

[INV-DEV-21] A Device Profile without an explicit ADB path uses the same platform default as the legacy configuration. The bundled executable takes precedence; explicit paths and explicit empty values remain unchanged through unrelated updates and save/reload.

## Implementation

`DeviceProfile.adb_path` and `Conf.maa_adb_path` share `default_adb_path` in the device configuration module. This removes inconsistent defaults without a second configuration migration or frontend path selection policy. Bundled paths retain the portable `@internal/platform-tools/` alias. Linux retains its environment and PATH defaults when the bundled executable is absent. Reading a default does not mark the Device Profile field as explicitly selected.

## Verification

Offline configuration tests cover Windows, macOS and Linux bundles, omitted paths, explicit custom and empty values, unrelated updates and save/reload. Device configuration and preflight tests check compatibility with existing selection and validation rules.

The additional session I/O suite reports the same 34 failures, including subtests, with both the shared default and the original empty default. These existing path and manager-fixture failures remain outside this change.
