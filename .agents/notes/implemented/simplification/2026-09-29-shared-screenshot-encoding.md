---
title: Shared Screenshot Encoding
status: implemented
category: simplification
date: 2026-09-29
---

# Shared Screenshot Encoding

[中文](2026-09-29-shared-screenshot-encoding.zh.md)

## Contract

[INV-DIAG-05] Shared Frame Encoding: Each admitted RGB snapshot has at most one encoding attempt; `ScreenshotStore` releases the source snapshot after that attempt, and preview, history and error context share its encoded bytes. Admission remains bounded and newer previews progress independently.

`ScreenshotStore` owns the encoding state for each immutable snapshot. The existing preview and writer workers share completion without encoding the same snapshot twice. A preview does not wait for an older frame owned by the writer. Encoding and file operations execute outside the store admission lock. The writer waits for a shared result only within the common shutdown deadline.

Completed snapshots retain JPEG bytes without the source RGB array. Legacy PNG files remain readable and subject to cleanup. Failed encoding retains a diagnostic description without an exception traceback or source array. Queue accounting follows the retained representation under the same lock as admission; encoded expansion obeys the existing capacity and protected-frame rules. Preview publication remains monotonic by capture time.

## Evidence and Verification

The preview and writer call the same encoder with the same captured frame. No external caller mutates screenshot metadata; the HTTP view reads encoded data and its timestamp. Shared per-frame state replaces duplicate transformation without adding a worker, global result cache, configuration field or domain term.

Offline tests measure encoding attempts, source-array lifetime during blocked writes, capacity during encoded expansion, preview progress, error-window contents and bounded shutdown. The [device control description](../../../../docs/subsystems/device-control.md#single-archive-limits) owns the current per-archive limits. Archive tests verify that pre-error recent context, stored history frames and ZIP exports carry the shared JPEG bytes and that legacy PNG files remain readable; image dimensions, JPEG quality and the sixteen-frame recent-cache count retain their existing values. A lossless PNG variant preserved exact pixels but increased encoding work and stored bytes, so completed snapshots retain the shared JPEG bytes; new archives no longer guarantee exact-pixel reproduction, while existing memory and disk bounds still apply.
