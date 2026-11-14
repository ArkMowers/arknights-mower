---
title: 复用单 Free 恢复分配
status: implemented
category: simplification
date: 2026-10-04
---

# 复用单 Free 恢复分配

## 契约

[INV-SCHED-20] 在仅有一个有效 Free 床位的宿舍住客离宿时，复用已有的单回分配投影。全部合格入住者参与本次事件。普通入宿保留现有分配，单纯心情变化保持原位。

## 简化

`prioritize_new_dorm_recovery` 已供换班重排和空床补位调用。离宿规划扩展其候选集合，不增加独立排序器、持久事件标记或配置选项。换班收敛和已确认清退复用同一投影边界。

## 验证

`dorm_single_free_departure_tests.py` 离线验证跨宿舍排序、重复投影、预约与已确认离宿入口，不执行设备或网络 I/O。
