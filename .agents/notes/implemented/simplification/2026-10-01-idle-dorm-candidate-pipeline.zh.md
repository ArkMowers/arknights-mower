---
title: 不养闲人共用候选流程
status: implemented
category: simplification
date: 2026-10-01
---

# 不养闲人共用候选流程

[English](2026-10-01-idle-dorm-candidate-pipeline.md) | [中文](2026-10-01-idle-dorm-candidate-pipeline.zh.md)

## Contract

不养闲人的任务生成与实际选人共用候选快照和预约规则。候选快照明确区分未回满的有效读数、已核验满心情读数和未知读数。保留满心情原住客前，未知读数通过游戏心情升序选人核验。

简化审查确认 `try_add_release_dorm` 与 `get_dorm_candidates` 重复收集预约、未知读数混入满心情候选，以及独立的原住客兜底分支。两个调用方共用 `dorm_task_reservations`，`DormCandidates` 统一三种状态，既有选人和读回流程负责核验与搜索节流。统一宿舍策略没有旧模式分支，也不增加配置。

空床优先安排需要恢复的合格候选，再安排已核验满心情者。救急先安排主班，仅补未预约的剩余空床。正式未完成恢复住客保床，临时补位者可让床。加工使用独立任务，入队与调人共用材料检查。恢复现场成功后的事件与日常规划共用恢复入口；单人和合并清退共用派发时的计时复核。各住客的实测回满时刻驱动清退，主班入住保留床位优先级规则。
