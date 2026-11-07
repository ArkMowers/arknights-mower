---
title: 复用现有恢复与配置职责
status: implemented
category: simplification
date: 2026-09-29
---

# 复用现有恢复与配置职责

[English](2026-09-29-review-recovery-ownership.md)

## 依据与契约

`DeviceSettings.edit` 是 `editedDevicePatch` 唯一的生产调用方。它以已保存配置作为比较基准复用该函数，维持后端配对，并且不从草稿复制身份字段。

`DeviceControl.capture` 是 `_standard_adb_ready` 唯一的调用方。目标检查使用会话已有的就绪分类，不创建已替换的截图助手。正常截图不需要已结束恢复事务的期限。

`BaseSolver.restart_game` 已负责游戏退出、启动和识别缓存失效。场景恢复在设备恢复后复用该操作，不增加模拟器命令分派。

修复沿用这些既有职责，不增加配置代理、后端注册表或通用期限服务。验证边界为 [INV-01]、[INV-04]、[INV-DEV-07] 和 [INV-REC-03]。

## 验证

组件测试验证已保存后端配对与身份保持；截图测试验证正常操作独立期限与目标检查；场景测试验证单次重启和终止异常传递。
