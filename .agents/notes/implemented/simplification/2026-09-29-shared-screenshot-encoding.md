---
title: Shared Screenshot Encoding
status: implemented
category: simplification
date: 2026-09-29
---

# Shared Screenshot Encoding

[中文](2026-09-29-shared-screenshot-encoding.zh.md)

## Contract

[INV-DIAG-05] Shared Frame Encoding: Each admitted RGB snapshot has at most one encoding attempt; preview, history and error context share its encoded bytes, release the source snapshot after completion, and preserve bounded admission and independent progress of newer previews.

`ScreenshotStore` owns the encoding state for each immutable snapshot. The existing preview and writer workers share completion without encoding the same snapshot twice. A preview does not wait for an older frame owned by the writer. Encoding and file operations execute outside the store admission lock. The writer waits for a shared result only within the common shutdown deadline.

Completed snapshots retain JPEG bytes without the source RGB array. Failed encoding retains a diagnostic description without an exception traceback or source array. Queue accounting follows the retained representation under the same lock as admission; encoded expansion obeys the existing capacity and protected-frame rules. Preview publication remains monotonic by capture time.

## Evidence and Verification

The preview and writer call the same encoder with the same captured frame. No external caller mutates screenshot metadata; the HTTP view reads encoded data and its timestamp. Shared per-frame state replaces duplicate transformation without adding a worker, global result cache, configuration field or domain term.

Offline tests measure encoding calls, source-array lifetime during blocked writes, capacity during encoded expansion, preview progress, error-window contents and bounded shutdown. Image dimensions, JPEG quality and the sixteen-frame recent cache retain their existing values.
