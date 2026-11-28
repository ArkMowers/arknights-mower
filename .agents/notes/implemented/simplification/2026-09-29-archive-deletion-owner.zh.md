---
title: 归档删除的唯一责任方
status: implemented
category: simplification
date: 2026-09-29
---

# 归档删除的唯一责任方

[English](2026-09-29-archive-deletion-owner.md)

## 契约

`ScreenshotStore` 负责报错归档的删除、容量计数和待写任务。`ScreenshotCleanup` 分批清理普通 Capture Frame 文件，将报错归档留给其责任方。

## 依据

`ScreenshotStore._clean_error_archives` 通过 `_delete_error_archive_locked` 处理过期和容量限制，删除入口持有归档锁并撤销待写任务。存储层是 `ScreenshotCleanup` 唯一的生产调用方，没有外部接口依赖第二套归档删除实现。

存储层在同一次归档候选遍历中处理过期和容量限制。普通截图清理器不再重复扫描归档大小或直接删除归档。

## 验证

`arknights_mower/tests/screenshot_tests.py` 验证过期、降低容量、撤销待写任务和拒绝迟到截图。`arknights_mower/tests/screenshot_cleanup_tests.py` 验证截图分批清理和无关文件保留。
