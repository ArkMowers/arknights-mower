---
title: 训练列表阴影末列
status: implemented
category: bug-fix
date: 2026-10-12
---

# 训练列表阴影末列

[English](2026-10-12-shadowed-training-column.md) | [中文](2026-10-12-shadowed-training-column.zh.md)

## 契约

**[INV-REC-13] Shadowed Training Column** 遵循[训练选人契约](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants)。姓名框几何信息来自实际边界，干员身份来自现有模板匹配器。

## 证据与实现

10 月 12 日 12:45 的 fui 归档在按住及稳定后的训练选人画面中均包含褐果。按住画面能够识别褐果；抬手后，右下角背景亮度低于分割阈值 85，稳定画面漏掉姓名框，尽管姓名完整可见。重复搜索最终报告未找到干员。样例只保留两条原始 RGB 姓名横带，不包含账号面板：[按住横带](../../../../arknights_mower/tests/fixtures/selection/training_chestnut_held_bands_20261012.png)与[稳定横带](../../../../arknights_mower/tests/fixtures/selection/training_chestnut_settled_bands_20261012.png)。

`operator_list_train` 保留完整姓名框的现有分割。末尾未配对的左边界仅在最右列借用另一行完整姓名框的范围，且两行左边界位移不超过三个像素。补全范围保留自身行坐标与位移。两行边界均来自同一 Capture Frame，不把按住时的坐标带入后续观察。模板匹配、特别关注归一化、缓存、输入及观察时序均保持现有行为。

前置简化检查未发现冗余抽象：共享训练识别器同时服务选人扫描与验证。修正在现有逐行分割及姓名匹配内完成，不增加独立检测器或重试路径。纯识别修正无需修改术语表。

## 验证

[离线回归](../../../../arknights_mower/tests/training_tail_name_tests.py)重放归档横带，覆盖任意一行受阴影影响，保持输入像素不变，拒绝缺失参照、错位与裁切，并保留未知姓名拒绝。扫描测试使用实际姓名识别器和替代输入、观察，覆盖 medium、high、xhigh 模式。按住至稳定的路径经过两次新观察，在褐果的新位置选中，不再次滑动。位移对照在对齐容差内保留各行的实际坐标。

## Standards Findings

PASS：修正在共享训练识别器内完成，不增加配置或资源，保留现有匹配阈值与输入像素，不增加截图或输入路径。变更 Python 文件通过 Ruff 检查及格式检查。治理检查通过，保留两条已有归档引用兼容性警告。

## Spec Findings

PASS：新增归档画面回归在修正前失败，修正后通过。针对性识别、姓名缓存、训练卡片、末页抬手、页面身份、右缘、ROI 及治理测试共通过 341 项测试和 471 个子测试。六张现有训练 JPEG 样例的差异重放保留全部 35 组既有姓名与坐标，且未新增检测。验证仅使用离线画面和替代设备输入。
