---
title: 有界截图存储、历史记录与实时预览
status: implemented
category: architecture
date: 2026-09-27
---

# 有界截图存储、历史记录与实时预览

[English](2026-09-27-bounded-screenshot-storage-and-preview.md) | [中文](2026-09-27-bounded-screenshot-storage-and-preview.zh.md)

## 1. 背景与动机
在原有实现中，主线程在 `Device.screencap()` 中同步执行 JPEG 编码，且历史队列和归档任务缺乏严格的原始帧容量上限，慢速磁盘或高频截图容易造成主流程卡顿与内存膨胀。

本次重构在保留原有错误归档能力的基础上，优化了底层数据流：将 JPEG 编码移至后台独立线程，为主线程识别、Web 实时预览与历史写盘提供隔离的有界内存额度与优雅退出排空机制。

---

## 2. 不变式与保证

- **[INV-01] 识别主流程零阻塞**：主线程 `Device.screencap()` 仅执行采集与灰度转换，不执行同步 JPEG 编码、目录遍历或文件 I/O。
- **[INV-02] 预览单槽位覆盖**：预览采用单槽位覆盖模式（最新的普通截图覆盖尚未消费的旧帧），历史写盘积压或慢速磁盘绝不阻塞 Web 实时预览刷新。
- **[INV-03] 有界内存与容量保护**：历史队列上限为 128 张或 64 MiB 输入原始帧；错误归档任务上限为 128 项（超出累计 `archive_dropped`）。达到上限时优先淘汰最旧的普通/调试截图；业务关键截图与错误窗口帧受保护不淘汰。
- **[INV-04] 限时排空与丢弃统计**：进程退出时提供至多 5 秒优雅写盘排空预算，超时未落盘的排队帧主动丢弃并累计 `shutdown_*_dropped` 指标，不阻塞进程退出。

---

## 3. 数据流与管道架构

```text
设备截图 → RGB、灰度 → 自动识别
               ↓ 复制不可变原始帧
               ├─ 单个覆盖槽位 → 预览编码线程 → 内存 JPEG → 网页 (GET /screenshot/latest)
               └─ 有界历史队列 → 历史编码与写盘线程 → 轮转磁盘归档 (screenshot/YYYYMMDD-HH/)

独立错误归档线程 → 捕捉 ERROR 日志 → 归档报错前后各 5 分钟画面至 screenshot/errors/<timestamp>/
独立磁盘清理线程 → 周期性游标清理超期截图 (间隔 1 小时)
```

---

## 4. 接口与存储布局

### 4.1 目录规范
- **普通历史截图**：`screenshot/YYYYMMDD-HH/<nanosecond_timestamp>.jpg`
- **业务关键截图**：`screenshot/{run_order,workshop,furniture,solve_captcha}/<nanosecond_timestamp>.jpg`（保留最近 100 张）
- **错误归档截图**：`screenshot/errors/<timestamp>/`（保留关联日志 `logs.json` 与前后 5 分钟画面）

### 4.2 Web 预览接口
- `GET /screenshot/latest`：需携带 Token 认证。
  - 无新帧时返回 HTTP 204；
  - 携带匹配 `If-None-Match` 时返回 HTTP 304；
  - 成功时直接返回内存 JPEG 二进制流。
- `GET /screenshot/stats`：返回存储健康度指标（`pending_bytes`、`dropped`、`preview_age`、`write_ms` 等）。

---

## 5. 验证与测试

- 单元测试：`screenshot_tests.py`、`screenshot_pipeline_tests.py`、`screenshot_cleanup_tests.py`、`screenshot_integration_tests.py`
- 前端测试：`ui/src/utils/screenshotPreview.test.js`
- 覆盖项：磁盘慢速模拟、满队列丢弃与计数、临时文件原子重命名、关闭时 5 秒优雅排空。
