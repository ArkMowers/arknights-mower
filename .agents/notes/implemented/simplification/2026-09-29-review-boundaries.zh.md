---
title: MuMu 解析与设置状态复用
status: implemented
category: simplification
date: 2026-09-29
---

# MuMu 解析与设置状态复用

[English](2026-09-29-review-boundaries.md)

ADB 端点查询和 IPC 预检重复处理三种 JSON 结构，身份匹配规则存在差异。共用解析器校验显式实例身份、已保存的名称和端点格式。发现流程复用相同的 JSON 结构归一化。

设置页通过一个可写计算属性，从三个持久化标记派生空闲动作。RecoveryPolicy 已定义 poll_interval，绑定时直接访问该字段。

性能策略和求解器已消费性能反馈全局变量。io_timeout 调用当前截止时间回调。配置的同步遍历收集 Vue watchEffect 依赖。这些机制保持有效。

[修复契约](../bug-fix/2026-09-29-review-command-isolation.zh.md)定义行为与验证。现有词汇表定义保持不变。
