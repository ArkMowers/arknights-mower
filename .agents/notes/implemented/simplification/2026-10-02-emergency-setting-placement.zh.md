---
title: 智能救急设置位置
status: implemented
category: simplification
date: 2026-10-02
---

# 智能救急设置位置

## 契约

[INV-01] 保留既有配置绑定与默认关闭状态。智能救急勾选项仅出现在 Mower 设置卡片中，紧接显示主题。MAA 设置表单移除该勾选项及未使用的绑定。设置页面使用既有配置自动保存。

两个既有组件之间移动控件，不增加配置字段、迁移或包装。[恢复生命周期](../../implemented/simplification/2026-10-02-native-automatic-rescue.zh.md)定义 Mower 临时驻员与实测恢复。

## 审查与验证

Standards Findings：控件复用配置存储与默认关闭状态，配置字段和恢复行为保持一致。

Spec Findings：名称使用“智能救急”，使用勾选框和旁侧帮助。配置存储专项测试、前端生产构建及治理检查验证设置移动。

验证：移动后的配置存储套件通过 17 项测试。生产构建与所有治理门禁通过；治理单测通过 14 项测试和 4 项子测试。
