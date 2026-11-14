---
title: MuMu Native Back Dispatch and Input Transport Attribution
status: implemented
category: bug-fix
date: 2026-09-28
---

# MuMu Native Back Dispatch and Input Transport Attribution

[English](2026-09-28-mumu-native-back-dispatch.md) | [中文](2026-09-28-mumu-native-back-dispatch.zh.md)

## Contract

- **[INV-DEV-01] Native Back Dispatch**: When the selected touch backend is MuMu IPC, Android BACK uses the owned MuMu IPC worker; an uncertain result stops the session without input replay or ADB fallback.
- Other Android keycodes retain the ADB transport. Failure diagnostics identify the actual input transport independently of the selected touch backend.
- `[INV-03]` preserves Instance Binding on failure; `[INV-04]` preserves the paired MuMu IPC capture and touch selection.

## Implementation

`Device.send_keyevent(4)` selects the transport from the configured touch backend and invokes the existing `MuMuInputSession.back()` through `Device._input_once`. A temporary absence of the control helper during recovery does not change transport selection; the operation waits for the session lock before using the restored helper. The native helper maps Android BACK to MuMu key `1` and uses the existing bounded worker for key down and key up. Either native event failure terminates input delivery without replaying the gesture.

`TouchFailure` retains the selected backend as metadata and accepts the actual input transport for diagnostics. ADB failures name ADB and direct the user to check the ADB connection. They do not suggest unrelated touch backend changes.

The note validator accepts both core invariant identifiers (`[INV-01]`) and subsystem identifiers (`[INV-DEV-01]`), matching the documented invariant registration contract.

The [pre-flight simplification audit](../simplification/2026-09-28-reuse-mumu-back-dispatch.md) establishes reuse of the existing native entry point. The [device subsystem contract](../../../../docs/subsystems/device-control.md) owns the permanent dispatch and failure rules.

## Verification

Offline tests cover MuMu BACK routing, native transport selection while recovery temporarily removes the control helper, native key mapping, failures during key down and key up, session termination, absence of ADB replay, unchanged ADB routing for other keycodes, and actual-transport error attribution. The focused suites are `device_touch_tests.py`, `device_mumu_input_tests.py`, and `verify_governance_tests.py`.
