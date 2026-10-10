---
title: 休眠恢复保留场景超时检测
status: implemented
category: bug-fix
date: 2026-10-08
---

# 休眠恢复保留场景超时检测

## 范围

**[INV-REC-08] 休眠观测边界**：调度器成功恢复休眠时，丢弃缓存的标准画面帧和场景状态，重新开始连续场景与加载观测；休眠时长不计入场景超时，常规截图刷新和活动期观测继续保留冻结检测。

[基建调度契约](../../../../docs/subsystems/base-scheduler.md)定义此边界。设备身份、关闭授权和恢复预算继续遵循既有契约。

## 证据

[证据快照](../../../../arknights_mower/tests/fixtures/scheduler_incident_20261008.json)标明以下运行事件：

| 时间 | 观测 |
| --- | --- |
| 10:55:38.643 | 调度器等待 298.417708 秒，直到下一个任务开始。 |
| 10:56:15.034 | 休眠期间完成资源更新。 |
| 11:00:37.237 | 恢复后的首次观测识别为基建全局视角。 |
| 11:00:37.239 | `Recognizer.check_freeze` 报告场景超时并退出游戏。 |

捕获配置中的 `run_order_delay` 为 3 分钟。`check_freeze` 使用 `run_order_delay * 90`，对应 270 秒。正常休眠本身已经超过该阈值。

## 原因

捕获基线 `87b9d3aa` 中的 [`_idle_sleep`](../../../../arknights_mower/solvers/base_schedule.py)结束时调用 `recog.update()`。[`Recognizer.update`](../../../../arknights_mower/utils/recognize.py)使标准画面帧和场景缓存失效，但保留 `last_scene` 与 `last_scene_time`。正常休眠后识别到相同场景时，未观测的休眠时间被计入连续场景停留时间。

该基线中的 `rest_until_next_task` 在等待前清空 `last_scene`；`BaseSchedulerSolver.run` 内的等待直接调用 `_idle_sleep`，缺少同样的复位。日志中的警告来自 `check_freeze`，而非加载场景的等待流程。离线场景将资源刷新替换为空操作后仍然触发该问题。

## 实现边界

`_idle_sleep` 在成功恢复时调用现有 `Recognizer.reset_after_external_control`。该操作使缓存的标准画面帧和场景失效，清空 `last_scene`，重置观测时间戳和加载观测次数。下一次识别取得新的标准画面帧。等待结束后，模拟器启动或重连失败时，观测边界保持待完成状态；[`_resume_device_dispatch`](../../../../arknights_mower/__main__.py)仅在设备恢复成功后完成识别复位。HTTP 唤醒、维护等待、模拟器恢复和 `sleeping` 生命周期保留既有顺序。停止信号和恢复错误在恢复识别之前传播。

四个正式等待入口共用 `_idle_sleep`：`BaseSchedulerSolver.run`、`rest_until_next_task`、MAA 异常处理及 `__main__._handle_maintenance`。统一边界复用现有识别复位操作，并删除 `rest_until_next_task` 中重复的 `last_scene` 赋值；不添加包装层或识别接口。常规 `Recognizer.update`、`BaseSolver.sleep` 和活动期设备恢复继续保留场景超时检测。本次修复沿用既有标准画面帧与调度概念。

## 验证

[事件回放](../../../../arknights_mower/tests/scheduler_incident_20261008_tests.py)用固定时钟执行真实 `_idle_sleep` 和 `check_freeze`。原回归在修复前收到一次错误的游戏退出调用，修复后没有退出调用。

[休眠观测测试](../../../../arknights_mower/tests/idle_scene_watchdog_tests.py)在正常到期、提前唤醒与维护等待后，使用模拟标准画面帧执行生产识别和按需截图。恢复时排除 298.417708 秒休眠区间。活动期观测恰好达到 270 秒时允许该场景，达到 271 秒时退出游戏；`Recognizer.update` 与 `BaseSolver.sleep` 刷新画面后仍遵守该规则。

同一测试还执行 `rest_until_next_task` 与 `__main__._handle_maintenance`，经过 600 秒等待、启动或重连失败、`_resume_device_dispatch` 和 `BaseSchedulerSolver.run`。首次生产观测取得新画面，不退出游戏。恢复尝试失败及取消时不改动识别状态，设备成功恢复后才完成复位；后续活动期恢复保留观测时间戳。在审查提交 `f2a99d312c1a714384a12473a05b68761a6e82ca` 上，这些新增用例产生五项失败；修复待完成边界后，全部十一项休眠观测用例通过。

现有模拟器生命周期、MAA 交接与[设备恢复监督测试](../../../../arknights_mower/tests/device_recovery_supervision_tests.py)覆盖恢复顺序、常规截图刷新、有限重试预算及停止传播。

```text
python -m pytest arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'idle or scheduler_sleep' -q
python -m pytest arknights_mower/tests/idle_scene_watchdog_tests.py arknights_mower/tests/maa_scene_handoff_tests.py -q
python -m pytest arknights_mower/tests/base_scheduler_tests.py -k 'TestIdleSimulatorWake or idle_sleep_wakes' -q
```
