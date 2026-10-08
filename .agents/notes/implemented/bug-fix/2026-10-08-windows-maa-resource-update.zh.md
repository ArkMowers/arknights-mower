---
title: Windows MAA 资源更新
status: implemented
category: bug-fix
date: 2026-10-08
---

# Windows MAA 资源更新

## 契约

[INV-UPD-04] 通过现有前端控件和资源接口，为已安装的 Windows MAA 提供独立资源检查与更新。GitHub 和 Mirror酱复用 macOS、Linux 的增量合并、资源备份及 MAA 使用中保护。

## 简化

资源信息、检查、启动和安装函数使用一致的支持平台范围，移除过时的 Windows 手动更新提示。现有前端直接使用 `supported`，不新增界面状态、配置或安装抽象。

## 验证

定向离线测试覆盖 Windows 资源信息、两种更新源、成功检查前置条件、工作线程平台传递、核心和 Python 文件保留、增量资源、备份及 MAA 使用中拒绝更新。现有合并与回滚测试继续约束安装行为。

## 审查

规范审查：安装复用现有事务锁、有时限的下载和回滚。需求审查：已安装的 Windows MAA 显示独立资源更新控件，并完成与其他桌面平台一致的更新流程。
