---
title: 恢复退出清理与任务保留
status: implemented
category: bug-fix
date: 2026-10-01
---

# 恢复退出清理与任务保留

## 契约

[INV-DEV-19] 在进程退出和空闲清理期间保留共享 ADB 服务运行。[设备控制](../../../../docs/subsystems/device-control.md) 定义应用自有辅助资源释放、延后清理与幂等关闭。[共享 ADB 恢复提案](../../proposed/simplification/2026-10-01-shared-adb-recovery.zh.md)替代本记录的前台服务所有权与监听验证部分；辅助资源清理和任务保留仍然有效。

[INV-SCHED-13] 覆盖恢复后的调度器入口，不仅覆盖恢复函数返回。[基建调度](../../../../docs/subsystems/base-scheduler.md) 定义未来显式任务保留与过期排班重建。

## 简化

现有退出标记区分最终释放与普通空闲清理。现有调度清理条件保留未来显式任务，不增加任务来源字段、第二个队列或独立恢复调度器。关键预约与普通排班规则仍集中在 `handle_error`。

桌面操作系统矩阵使用替代资源执行共享 ADB 应用恢复、辅助资源退出清理与调度任务保留回归测试，不检查监听所有权或执行宿主机命令。

## 验证

`device_control_shutdown_tests.py` 覆盖活跃操作期间的退出、延后辅助资源清理、补偿顺序与幂等释放。`device_adb_recovery_tests.py` 覆盖同目标辅助服务重建、其他进程重启代次、取消、动作预算与不关闭共享恢复协调器的清理。

`scheduler_recovery_preservation_tests.py` 覆盖过期排班边界、关键预约、任务数据保留、真实调度分发及工作线程从恢复到调度的衔接。

不修改真实设备、远端配置、设备配置结构或术语定义。
