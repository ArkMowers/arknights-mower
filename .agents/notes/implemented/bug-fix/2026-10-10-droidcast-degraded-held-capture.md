---
title: DroidCast Degraded Held Capture
status: implemented
category: bug-fix
date: 2026-10-10
---

# DroidCast Degraded Held Capture

## Contract and complexity assessment

The repair preserves [INV-DEV-07], [INV-DEV-17] and [INV-DEV-24]. Held Capture Frames use the session's effective backend once without recovery, readiness mutation or input replay. Capture failure and an unavailable independent input helper require complete helper recovery; input-only repair does not count as screenshot reconstruction.

`Device.screencap(recover=False)` bypasses `ScreenshotSession.degraded` and calls the selected DroidCast helper after ordinary capture has degraded to ADB. `DeviceControl.capture` also interprets any recovery action as screenshot reconstruction, including input-only repair. The repair keeps backend selection at the application boundary and reuses existing capture, helper cleanup and Recovery Budget mechanisms. No queue, worker, second fallback policy or new invariant is required. Existing Capture Frame, Instance Binding and Recovery Budget terms retain their meanings.

The yunxi logs contain an idle simulator restart and subsequent ADB reconnection before repeated missing-mapping errors in held selection capture. They do not identify the operation that removes the original forward. Mapping diagnostics report the expected mapping and bounded observations for its local port; degradation reports its cause once at the transition.

## Verification

Offline regressions exercise ordinary capture followed by held selection capture after degradation, capture and input failure in the same recovery, cancellation, invalid frames, touch release and preservation of foreign mappings. See the [device contract](../../../../docs/subsystems/device-control.md) and [held capture decision](../../implemented/simplification/2026-10-09-held-swipe-capture.md).

`DeviceResult.helpers_rebuilt` distinguishes completed full helper reconstruction from input-only repair. A capture incident that repairs input still performs its permitted screenshot rebuild. `capture_once()` uses the application lock without draining deferred cleanup; the enclosing input operation drains it after release.

The two incident regressions fail before the repair. The focused DroidCast, held capture, screenshot backend, touch and device session suites pass 458 tests. The governance suite passes 27 tests, and Ruff and formatting checks pass for all five changed Python files. Structural governance passes with two existing warnings for missing suites referenced by the archived owned-ADB decision. These checks use offline substitutes and establish neither live-device reproduction nor the identity of the original forward-removal operation.

## Standards Findings

PASS: Existing invariant identifiers remain authoritative. Instance Binding, foreign forwards, persisted Device Profile and the input Recovery Budget remain preserved. The effective capture route introduces no thread, queue or parallel recovery policy. Existing glossary meanings remain unchanged; no glossary edit is required or made.

## Spec Findings

PASS: Degraded held capture returns the same-target ADB frame without invoking DroidCast or recovery. Capture and input failure in one incident repair both resources without miscounting input-only work as capture reconstruction. Invalid frames and capture failures retain structured reporting; cancellation and deferred cleanup release the touch before closing owned resources.
