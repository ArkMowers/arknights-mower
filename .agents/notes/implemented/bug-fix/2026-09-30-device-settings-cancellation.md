---
title: Device Settings Cancellation Isolation
status: implemented
category: bug-fix
date: 2026-09-30
---

# Device Settings Cancellation Isolation

## Contract

[INV-DEV-15] Settings Cancellation Isolation keeps device settings operations independent of a stopped task's cancellation signal. Process shutdown and device closure still cancel those operations. Cancellation reaches HTTP callers as a structured verdict, and the task stop signal remains unchanged.

## Boundary and simplification

Settings discovery, connection testing and all four startup entry points retain their shared Device Control boundary and Recovery Budget. A context-local cancellation scope covers synchronous readiness and capture-helper waits without clearing shared events or introducing another vendor startup implementation. Scope exit restores the caller's previous cancellation policy; concurrent task threads retain task cancellation.

The UI names the action `启动并检测`. It still checks the selected Instance Binding before issuing lifecycle commands and preserves the independent read-only connection test.

## Verification

Hermetic tests cover stopped-task settings startup with the production clock, helper waits, cancellation-scope restoration and thread isolation, shutdown during startup, structured HTTP cancellation, and task cancellation after a settings request. Existing instance selection and startup budget tests remain authoritative.
