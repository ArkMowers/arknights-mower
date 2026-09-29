---
title: macOS MuMu Pro Compatibility Entry & Evidence Matrix
status: implemented
category: feature
date: 2026-09-26
---

# macOS MuMu Pro Compatibility Entry & Evidence Matrix

[English](2026-09-26-mumu-pro-macos-compatibility.md) | [中文](2026-09-26-mumu-pro-macos-compatibility.zh.md)

## 1. Context & Motivation
MuMu Pro is NetEase's Android emulator for macOS. The bundled `mumutool info` command exposes a bounded instance list and a per-instance query on the tested installation. The compatibility preset retains manual ADB serial configuration for environments where that output cannot be verified.

---

## 2. Invariants & Guarantees

- **[INV-01] Rejection of Untrusted Endpoints**: Prior to verified `mumutool info` contracts, guessing endpoints or adopting foreign online ADB devices is strictly forbidden.
- **[INV-02] Guided Manual Configuration**: Failed discovery returns actionable guidance; the MuMu Pro preset accepts a user-specified ADB serial.
- **[INV-03] Unified Preflight Gate**: The selected endpoint passes standard read-only preflight (boot completion, 1920x1080 canvas frame, package detection).
- The [manual binding repair](../bug-fix/2026-09-30-mumu-pro-manual-binding.md) restores connection under this preset while keeping manager operations unavailable.
- The [instance selection decision](2026-09-30-mumu-pro-instance-selection.md) adds read-only discovery and per-instance identity checks.

---

## 3. Evidence Matrix Template

| Field | Content |
| :--- | :--- |
| **Audit Date & Env** | Timestamp, macOS version, Architecture (Apple Silicon / Intel) |
| **MuMu Pro Version** | App version, Build number, `mumutool` version |
| **Sanitized Output** | Raw output of `mumutool info all` and `mumutool info <index>` |
| **ADB & Display** | ADB version, `sys.boot_completed`, logical and physical frame size |
| **Verdict** | Meets automated discovery criteria or requires manual guidance |

---

## 4. Verification

- Unit tests: `device_mumu_pro_tests.py`, `device_mumu_pro_route_tests.py`.
- Tested branches: Manual guidance routing, endpoint cleanup upon preset switch, preflight gating.
