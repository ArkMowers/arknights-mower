---
title: MuMu 12 运行时目录布局的管理器解析
status: implemented
category: bug-fix
date: 2026-10-07
---

# MuMu 12 运行时目录布局的管理器解析

## 契约

MuMu 12 检测与 IPC 共享管理器位置和安装根目录推导。根级 `shell`、`nx_main` 目录属于其父目录；`temp/<pair>`、`.backup/<pair>` 属于其祖父目录，且优先识别运行时目录对。显式管理器路径保留选中的可执行文件。同一安装的注册表与进程来源只生成一个候选。

## 缺陷

管理器位于 `temp/main` 或 `temp/shell` 的版本需要相应搜索位置。重复的根目录推导会把运行时目录留在绑定中，产生重复候选和错误的 ADB 或 IPC 路径。

## 实现

`mumu_layout.py` 包含一份管理器位置清单和 `installation_root()`。检测与 IPC 对目录和管理器父目录均调用该函数。运行时父目录名精确匹配 `temp` 或 `.backup`。位置解析不执行管理器命令；调用方保留各自的文件检查和管理器缺失行为。

## 验证

`device_mumu_io_tests.py` 覆盖根目录、卸载程序、运行时目录、播放器及管理器来源，以及去重和显式管理器优先级。`device_mumu_capture_tests.py` 覆盖根级及运行时布局、备份目录对和相似运行时目录名的拒绝。所有用例使用临时文件和模拟的管理器输出。
