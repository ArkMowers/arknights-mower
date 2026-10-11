---
title: MAA 调用验证
status: implemented
category: simplification
date: 2026-10-11
---

# MAA 调用验证

[English](2026-10-11-maa-call-verification.md)

**[INV-MAA-08] Verified MAA Admission**：资源加载、任务提交和任务启动均要求 MAA 返回成功结果；调用被拒绝时明确失败阶段与目标，清理待执行任务且不记录执行成功，并保留回退备份。

简化审计确认 `VerifiedAsst` 是桌面端和安卓端现有的任务提交与启动公共边界。调度器负责普通任务、长任务和可选的主题恢复。复用这个边界消除各调用点分别处理返回值的需要。两端初始化均下载活动导航。桌面端通过 `Asst.load` 加载；安卓端通过 `maa_navigation` 将校验后的文件交给宿主，由宿主在空闲时加载到当前组件。旧宿主复用组件打包，当前加载组件未包含导航时要求重启服务，并提示更新 APK 后可直接加载；旧宿主兼容路径继续可用。配置结构和领域术语没有变化。

导航下载先验证非空 JSON 对象，再通过现有 `write_json` 原子替换。下载完成和 MAA 资源加载成功分别记录日志。桌面端初始化在构造句柄之前检查 `Asst.load`，并记录核心版本、资源时间戳和所选资源路径。

`MaaCallError` 携带失败阶段以及可选的任务类型与关卡。`VerifiedAsst` 拒绝非正任务编号和被拒绝的启动。调度器在普通异常路径释放已排队任务，停止失败时保留原始诊断。调用被拒绝不会更新上次执行时间或清理回退备份。已有取消和设备故障保留其异常类型并继续传播。

安卓资源更新复用现有 MirrorChyan MaaResource 安装器，与官方安卓核心组件来源分别选择。资源来源改变时作废已有更新检查凭据。不新增配置字段或领域概念。

[MAA 集成规范](../../../../docs/subsystems/maa-integration.md) 定义接口契约。`maa_admission_tests.py` 的离线回归覆盖部分提交后的拒绝、资源加载失败和无效下载；`maa_backup_tests.py` 覆盖回退备份保留。
