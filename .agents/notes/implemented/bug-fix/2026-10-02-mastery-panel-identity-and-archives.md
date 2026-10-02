---
title: Training Panel Identity and Failure Archives
status: implemented
category: bug-fix
date: 2026-10-02
---

# Training Panel Identity and Failure Archives

[English](2026-10-02-mastery-panel-identity-and-archives.md) | [中文](2026-10-02-mastery-panel-identity-and-archives.zh.md)

## Contract

- **[INV-REC-05] Training Panel Identity**: Training confirmation treats an unrecognized operator name or missing skill as unknown, retries within its existing deadline, and never derives actual occupancy from the requested plan.
- **[INV-DIAG-06] Error Notification Evidence**: Every ERROR notification emits a log record before mail configuration checks or delivery; screenshots are archived only when the caller explicitly identifies a visual failure, independently of email enablement.

## Evidence and implementation

The supplied alpha.10 notification reports Ptilopsis's second skill, Enkephalin, at mastery tier one, but the observed name is `白面`. The attachment contains a notification rather than a Capture Frame; it establishes the truncated name and missing archive report without proving the original pixel layout.

The reader retries invalid names with thresholded pixels. If both OCR passes omit one character, a candidate whose full name differs by exactly that omission and whose skill agrees with the OCR must pass the existing full-name and skill templates on the same Capture Frame. Only one confirmed candidate replaces the OCR name. Unavailable, stale, conflicting or ambiguous templates preserve uncertainty.

Training confirmation checks readable identity before testing plan disagreement. Unknown readings consume the existing confirmation deadline without writing `training` or issuing a false occupancy mismatch. Confirmed disagreement retains the failed status and notification. `send_message` logs every ERROR notification before checking mail configuration or preparing delivery. Its keyword-only `archive_screenshots` argument defaults to false; training arrangement rejection and confirmation timeout explicitly request screenshots, while ordinary configuration and transport notifications only log. Custom subjects preserve the body in the diagnostic detail. INFO and WARNING retain their existing behavior. Training failure and timeout exits use this shared boundary without additional archive records. Existing screenshot-window merging retains one archive for adjacent records.

Pre-flight simplification finds no removable public abstraction. The existing reader, template recognizer, notification entry point and archive handler remain the production boundaries. The readability gate precedes the disagreement gate, and the fix introduces no alternate archive store, plan-derived identity or retry budget. Explicit archive selection follows the existing log policy for visual failures.

The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns the identity guarantee; the [device diagnostics contract](../../../../docs/subsystems/device-control.md) owns ERROR notification evidence. Existing domain definitions remain accurate; no glossary change is required.

## Verification

Focused offline tests cover omitted characters in `白面鸮`, same-frame template confirmation, invalid and conflicting evidence, bounded confirmation, actual occupant disagreement, and training failure and timeout notifications reaching the archive handler before delivery. Shared notification tests cover all mail thresholds, visual and nonvisual ERROR notifications, disabled mail without account settings, custom subjects, delivery preparation failure, and ordinary notification isolation. Additional operator cases verify the same omitted-name rule for Hairin and Carnelian. Existing panel, arrangement, log and governance tests protect adjacent behavior. Test rendering uses the bundled panel font; the supplied notification provides no original training Capture Frame for replay.

The focused suites pass 574 tests and 67 subtests covering identity, arrangement, notifications, screenshot storage and governance. Existing screenshot tests verify preceding and following frame preservation, disabled ordinary history, overlapping-window merging, archive retention and bounded storage. Ruff, diff whitespace and repository governance checks pass.

## Standards Findings

PASS: Identity comes from the Capture Frame and roster templates. The change uses existing finite confirmation and bounded screenshot storage, introduces no device operations or persisted configuration, and preserves the authoritative glossary. Invariants are registered in standards, subsystem contracts and the review checklist.

## Spec Findings

PASS: Repeated omitted-name OCR no longer declares a false occupant disagreement. Confirmed foreign occupants still fail; unresolved identity retains the existing timeout. Every ERROR notification logs before mail configuration and delivery preparation; only explicitly identified visual failures request screenshots. Ordinary notifications retain their existing policy. Verification uses rendered and existing offline frames and mocked notification transport.
