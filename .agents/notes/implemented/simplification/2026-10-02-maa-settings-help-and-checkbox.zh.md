---
title: MAA 设置帮助与勾选框
status: implemented
category: simplification
date: 2026-10-02
---

# MAA 设置帮助与勾选框

## 契约

桌面和 Android 的 MAA 设置表单将协助勾选框放在恢复主题设置之后。可见标签为 `协助救急`，勾选状态直接绑定 `maa_emergency_infrast_enable`。[INV-SCHED-09] 保留[恢复契约](../../implemented/simplification/2026-10-02-maa-assisted-emergency.zh.md)定义的独立、默认关闭设置。

恢复主题说明使用表单标签旁已有的 `HelpText` 问号控件。表单不再重复显示独立的主题说明段落。帮助内容沿用现有焦点和指针交互，不新增显示抽象。

## 审查

Standards Findings：已有配置引用负责持久化，共享帮助控件提供说明；调度不变式保持一致。

Spec Findings：协助位于主题设置之后，使用请求的标签和勾选框；恢复主题说明通过问号帮助提供。

验证：已有组件与配置专项套件通过 23 项测试。Prettier、差异检查和三个治理门禁通过。
