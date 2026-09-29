---
title: Archive Deletion Ownership
status: implemented
category: simplification
date: 2026-09-29
---

# Archive Deletion Ownership

[中文](2026-09-29-archive-deletion-owner.zh.md)

## Contract

`ScreenshotStore` owns error archive deletion, capacity accounting and queued writes. `ScreenshotCleanup` advances bounded batches of ordinary Capture Frame files and leaves error archives to their owner.

## Evidence

`ScreenshotStore._clean_error_archives` applies expiry and capacity rules through `_delete_error_archive_locked`, which holds the archive lock and cancels queued work. The store is the only production caller of `ScreenshotCleanup`; no external interface requires a second archive deletion implementation.

The store combines expiry and capacity enforcement in one pass over archive candidates. The ordinary frame cleaner has no duplicate archive size scan or direct archive deletion.

## Verification

`arknights_mower/tests/screenshot_tests.py` checks expiry, capacity reduction, queued-write cancellation and late-frame rejection. `arknights_mower/tests/screenshot_cleanup_tests.py` checks bounded frame cleanup and unrelated-file preservation.
