---
title: Preservation Repair Boundaries
status: implemented
category: simplification
date: 2026-09-29
---

# Preservation Repair Boundaries

[中文](2026-09-29-preservation-repair-boundaries.zh.md)

## Contract

Screenshot submission retains the existing bounded writer queue and background JPEG encoding. The same writer supplies the encoded recent cache when ordinary history is disabled. No additional worker or unbounded raw-frame cache is introduced.

Verified connection saves and authorized Temporary Preparation share the identity-then-endpoint save sequence. Both callers preserve the last successful save when the endpoint save fails. `Conf.updated` remains the authority for target clearance.

`DeviceSession` owns ADB resolution for its bound profile and remaining Recovery Budget. Preparation and readiness reuse the resolved path instead of introducing a second discovery policy. ADB service requests expose uncertainty after transmission instead of hiding it behind repeated commands.

The existing `simulator.wait_time` remains the launch protection setting. Recovery timeout and local observation windows retain their existing meanings; no duplicate persisted setting is added.

## Evidence and Verification

The screenshot writer already owns queued frames and encoding. Two frontend entry points save a confirmed device binding. Session observation already resolves ADB before transport verification. These boundaries support the [behavior repair contract](../bug-fix/2026-09-29-preservation-review-repairs.md).

Focused tests cover both frontend save callers, physical preparation, request uncertainty, encoded recent frames and bounded shutdown. The existing glossary definitions remain applicable; this change adds no domain term or configuration field.
