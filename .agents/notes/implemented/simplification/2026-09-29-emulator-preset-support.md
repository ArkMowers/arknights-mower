---
title: Emulator Preset Support
status: implemented
category: simplification
date: 2026-09-29
---

# Emulator Preset Support

[中文](2026-09-29-emulator-preset-support.zh.md)

The Windows MuMu menu contains one entry, **MuMu 12**. MuMu 6 discovery has one production caller in Windows discovery; its lifecycle adapter has one registration. Both are removed with their UI fields and product-specific ADB paths. Compatibility parsing alone accepts retired MuMu 6 selections as `manual.other`, clears the endpoint and game confirmation, and preserves explicit paths for manual reconnection.

LD screenshot enhancement accepts both LDPlayer 9 and 14 through the same capture implementation. Targeted offline tests cover their configuration, UI and capture boundaries. The [capture record](../feature/2026-09-29-ld-capture.md) contains the user-authorized local live verification for both versions.

Existing [INV-02] clears endpoints on preset changes, [INV-DEV-05] rejects incompatible vendor choices, and [INV-DEV-06] preserves LD instance identity and frame dimensions. These guarantees already cover this change; no new invariant or glossary definition is required.

Targeted tests cover retired configuration loading, absence of MuMu 6 discovery and lifecycle commands, LDPlayer 14 capture, incompatible vendors, and draft selection changes.

## Standards Findings

Pass: migration clears the retired endpoint without changing caller data or writing configuration files. Vendor restrictions remain enforced at UI, save and capture boundaries. LD instance binding, bounded worker lifetime and Shared ADB Guard remain unchanged. Governance and scoped Ruff checks pass.

## Spec Findings

Pass: Windows exposes one MuMu entry labeled MuMu 12, removes the MuMu 6 adapters, and enables LD screenshot enhancement for both LDPlayer presets. Targeted verification passes 189 Python tests with 177 subtests and 113 frontend tests.
