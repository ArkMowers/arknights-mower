---
title: Preparation failure isolation
status: implemented
category: bug-fix
date: 2026-09-30
---

# Preparation failure isolation

## Contract

[INV-DEV-09] Classified Failure Isolation requires classified device failures, including Temporary Preparation errors, to request owned resource cleanup and expose their structured verdict without requesting application shutdown. Failed compensation retains its recovery record. Unclassified internal faults retain coordinated shutdown.

## Boundary and simplification

`PreparationSession.validate` reports unreadable or incompatible input surfaces through `PreparationError`. The application classifier recognizes that existing exception alongside readiness, preflight, capture and input failures. The existing failure handler owns cleanup and status reporting; no additional recovery loop or exception wrapper is introduced. Persisted Device Profile values and one-run authorization remain unchanged.

## Verification

Offline tests use the real preparation and preflight pipeline with an application shutdown callback. Invalid input surfaces preserve their error code, restore display geometry, keep the application available, and allow a corrected retry. Separate tests retain coordinated shutdown for an unclassified internal fault.
