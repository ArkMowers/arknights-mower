---
title: Bounded Screenshot Storage, History & Real-Time Preview
status: implemented
category: architecture
date: 2026-09-27
---

# Bounded Screenshot Storage, History & Real-Time Preview

[English](2026-09-27-bounded-screenshot-storage-and-preview.md) | [中文](2026-09-27-bounded-screenshot-storage-and-preview.zh.md)

## 1. Context & Motivation
In legacy versions, the main execution thread performed synchronous JPEG encoding inside `Device.screencap()`. Unbounded history queues and archive tasks caused recognition stuttering and memory bloat on slow disks.

This architecture moves JPEG encoding to independent background worker threads, establishing bounded ring buffers, isolated Web preview channels, and graceful flush budgets upon shutdown.

---

## 2. Invariants & Guarantees

- **[INV-01] Non-blocking Recognition Path**: Main thread `Device.screencap()` performs only capture and grayscale extraction; synchronous JPEG encoding, filesystem traversal, and disk I/O are strictly excluded.
- **[INV-02] Single-Slot Preview Overwrite**: Real-time Web preview uses a single-slot overwrite buffer where newest frames replace unconsumed frames without disk I/O dependency.
- **[INV-03] Bounded Memory & Eviction**: History queue is capped at 128 frames or 64 MiB; error archive queue is capped at 128 tasks. Buffer overflow evicts oldest non-critical debug frames while protecting business-critical and error-window captures.
- **[INV-04] Bounded Shutdown Flush**: Process shutdown enforces a maximum 5s flush budget; queued frames exceeding the deadline are dropped and counted in `shutdown_*_dropped` metrics without stalling termination.

---

## 3. Data Pipeline & Architecture

```text
Device Capture -> RGB & Grayscale -> CV Recognition
                       | Immutable Copy
                       +-- Single Overwrite Slot -> Preview Worker -> In-Memory JPEG -> GET /screenshot/latest
                       +-- Bounded History Queue -> Disk Worker -> screenshot/YYYYMMDD-HH/*.jpg

Error Archive Worker -> Captures ERROR logs -> Archives +/- 5 min frames to screenshot/errors/<timestamp>/
Disk Cleanup Worker  -> Periodic cursor cleanup (hourly interval)
```

---

## 4. API & Storage Layout

### 4.1 Storage Layout
- **Routine History**: `screenshot/YYYYMMDD-HH/<nanosecond_timestamp>.jpg`
- **Critical Business**: `screenshot/{run_order,workshop,furniture,solve_captcha}/<nanosecond_timestamp>.jpg` (retains last 100)
- **Error Archives**: `screenshot/errors/<timestamp>/` (retains `logs.json` and +/- 5 min window)

### 4.2 Web Preview API
- `GET /screenshot/latest`: Requires auth token.
  - HTTP 204 if no new frame is available.
  - HTTP 304 if `If-None-Match` matches current ETag.
  - HTTP 200 with raw JPEG binary stream on fresh frame.
- `GET /screenshot/stats`: Returns telemetry (`pending_bytes`, `dropped`, `preview_age`, `write_ms`).

---

## 5. Verification & Tests

- Unit tests: `screenshot_tests.py`, `screenshot_pipeline_tests.py`, `screenshot_cleanup_tests.py`.
- Frontend tests: `ui/src/utils/screenshotPreview.test.js`.
- Tested branches: Simulated slow disk, bounded drop counting, atomic file rename, 5s shutdown flush budget.
