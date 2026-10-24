---
title: 启动恢复预算归属
status: implemented
category: bug-fix
date: 2026-09-29
---

# 启动恢复预算归属

[English](2026-09-29-startup-recovery-budget.md)

## 契约

[INV-DEV-03] 启动预算隔离：每次新的设备启动均在准备阶段前建立恢复预算；准备、就绪检查、验证及辅助组件初始化共用该截止时间，不继承上次运行的截止时间。

`DeviceSession.begin_budget()` 建立截止时间。`DeviceControl._start()` 绑定选定的设备配置，在获取准备资源前启动预算。`ensure_ready(deadline=...)` 保留该截止时间。取消、实例绑定与清理规则继续生效。

现有术语表中的恢复预算定义继续适用；此修改不增加领域术语或持久化配置字段。

## 验证

`arknights_mower/tests/device_session_tests.py` 覆盖旧截止时间之后再次运行、准备耗时从就绪检查预算扣除，以及准备耗尽预算后停止设备探测并释放资源。现有就绪检查和准备生命周期测试覆盖恢复与补偿。

本地环境缺少 pytest，定向测试使用 `python -B -m unittest`：30 项会话测试及 45 项准备、生命周期和治理测试通过。应用边界、调用方和实例启动检查通过 28 项；一项现有应用测试将 `build_global_plan(include_source=True)` 的返回值模拟为 `{}`，实际接口返回二元组。仅在内存中恢复修改前的启动方法后，该测试仍然失败。

标准审查通过预算上限、清理和目标身份检查。规格审查通过重复启动及准备与就绪检查共用截止时间检查。治理检查通过；本次离线验证不包含真实设备执行。
