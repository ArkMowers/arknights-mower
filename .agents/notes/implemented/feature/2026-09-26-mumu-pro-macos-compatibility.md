---
title: macOS MuMu Pro Compatibility Entry & Evidence Matrix
status: implemented
category: feature
date: 2026-09-26
---

# macOS MuMu Pro Compatibility Entry & Evidence Matrix

[English](2026-09-26-mumu-pro-macos-compatibility.md) | [中文](2026-09-26-mumu-pro-macos-compatibility.zh.md)

## 1. Context & Motivation
MuMu Pro is NetEase's Android emulator for macOS. Because the official CLI `mumutool info` output lacks public specifications, `macos.mumu_pro` is maintained as a documented compatibility preset providing guided manual configuration rather than unverified heuristic discovery.

---

## 2. Invariants & Guarantees

- **[INV-01] Rejection of Untrusted Endpoints**: Prior to verified `mumutool info` contracts, guessing endpoints or adopting foreign online ADB devices is strictly forbidden.
- **[INV-02] Guided Manual Configuration**: Discovery returns actionable guidance directing users to `manual.other` for explicit serial/port binding.
- **[INV-03] Unified Preflight Gate**: Manual endpoints must pass standard read-only preflight (boot completion, 1920x1080 canvas frame, package detection).

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
