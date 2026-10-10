---
title: MAA 回调日志
status: implemented
category: feature
date: 2026-09-30
---

# MAA 回调日志

[English](2026-09-30-maa-callback-logging.md)

`arknights_mower/utils/maa_callback.py` 把 MAA 核心回调消息转换为可读的运行日志行，`arknights_mower/solvers/base_schedule.py` 中的 `BaseSchedulerSolver` 在每轮 MAA 运行中消费该转换结果。[子系统规范](../../../../docs/subsystems/maa-integration.md) 规定运行边界与回调消费契约。

**[INV-MAA-01] 回调全量处理**：每个 MAA 回调都被消费且不抛异常；负载字段缺失、为空或无法识别时，在 C 回调边界最多产生一条诊断行，而不是抛出异常。

**[INV-MAA-02] 回调驱动 MAA 进度**：一轮 MAA 运行的运行日志以核心回调为进度来源——每次任务链状态变化与每个白名单里程碑各产生一行，轮询循环在每个间隔内最多贡献一条心跳行。

`parse_details` 解码单条回调明细负载；负载缺失、为空或无法解析时返回 `{}`，不会在 C 回调内抛异常。`MaaCallbackLog.describe` 把单条消息与负载映射为 `MaaLogLine(level, text)`，由调用方记录。措辞与级别均沿用 MAA 桌面客户端的回调处理逻辑，每个事件使用该客户端给出的级别；这样做的唯一副作用是：来自调度器模块的 ERROR 行还会归档截图。转换逻辑位于 `TASK_CHAIN_TEXT`、`CONNECTION_TEXT`、`SUB_TASK_INFO`、`PROCESS_TASK_START`、`PROCESS_TASK_COMPLETED`、`SUB_TASK_ERROR` 与 `REPORT_WHY_TEXT` 表中，覆盖本调度器提交的任务链——StartUp、Fight、Mall、Award、Recruit、Roguelike、SSSCopilot、Reclamation 与 SwitchTheme——并附带其他已知任务链。表查找先把键规整为字符串，类型异常的负载字段退化为缺省结论，因此没有未经防护的字段形态会到达转换表。

过滤策略让周期性遥测（`EmulatorFPS`、`FastestWayToScreencap`、`MuMuExtrasInputStatus`）与设施流量留在 DEBUG。`ScreencapCost` 没有可读结论，不产生日志行。`ProcessTask` 的子任务开始与完成行只对节点名白名单输出，这正是 MAA 客户端自身的防刷屏机制；其余节点不产生转换后的日志行。`SubTaskStopped`（20004）不产生日志行。`TaskChainStopped`（10004）会产生，因为主动停止 MAA 的那几个循环并非都会自行记录这次停止。

`MaaCallbackLog.heartbeat` 每个 `HEARTBEAT_INTERVAL`（60 秒）最多输出一条 INFO 行，说明正在运行的任务链与已运行时长；超过 `STALL_AFTER`（180 秒）没有收到任何回调时额外附上静默说明。构造参数 `interval`、`stall_after` 与 `clock`（默认 `time.monotonic`）可注入，测试注入假时钟。任务链在链路完成（10002）、停止（10004）或全部任务完成（3）时清空，因此已结束或已停止的链路都不会显示为仍在运行。

`initialize_maa` 在桌面路径与 `MOWER_ANDROID` 路径上都为每轮 MAA 运行建立新的 `MaaCallbackLog`，且位于校验后的 `Asst` 构造与连接调用之前，因此连接类回调同样被覆盖。`on_maa_callback` 是回调入口，负责解码负载、继续把结构完好的 `StageDrops` 累积到模块级 `stage_drop` 供现有 `maa_stop` 汇报使用，并按级别经调度器模块的 logger 记录转换后的日志行。每轮重置由 `reset_stage_drop` 统一负责，供 `maa_plan_solver` 与 `maa_stop` 共用。`report_maa_progress` 调用 `heartbeat()`，仅在间隔到达时记录。两个 MAA 轮询循环用 `self.report_maa_progress()` 取代原先每 5 秒一次的 `logger.info("MAA 运行中...")`。

旧回调是类级 `@CFUNCTYPE` 方法 `log_maa`，其三个 `Recruit*` 分支写入模块全局变量 `recruit_tags_selected`、`recruit_special_tags`、`recruit_results`。仓库中没有任何模块定义这些名字，因此这些分支在 ctypes 回调内抛出 `NameError`，而 ctypes 吞掉了该异常。没有任何代码消费这些状态，转换后的日志行取代了这些分支。未使用的 `Message` 导入与全局变量、未使用的 `ctypes` 与 `json` 导入，以及 `maa_update.clear_loaded_maa_cache` 中对应清空该全局变量的语句，一并从模块中移除。该方法改用现在的名字，是因为它同时承担代发上报的职责；该契约见[上报决策记录](2026-10-01-maa-report-upload.md)。

`arknights_mower/tests/maa_callback_tests.py` 通过注入的假时钟提供 59 个离线测试：负载解码、全部已知 `what` 与消息码上的错误字段类型、非字符串干员名、各类消息族、噪声过滤、心跳节流与静默文案、畸形掉落累积、每轮掉落重置，以及调度器接线，包括 `VerifiedAsst` 回调路由与 `initialize_maa` 建立新的汇报器。既有测试 `maa_error_no_exit_tests.py`、`maa_backup_tests.py`、`maa_restore_theme_tests.py`、`maa_scene_handoff_tests.py`、`maa_check_tests.py`、`base_scheduler_tests.py`、`maa_update_tests.py`、`stage_plan_scheduler_tests.py` 仍然通过。

`ReportRequest`（30000）本身没有可读的进度结论，因此本次改动把它的负载记入调试日志，请求本身交给[上报决策记录](2026-10-01-maa-report-upload.md)描述的上传路径。本机 `runtime.log` 记录到核心交出的请求指向 `https://penguin-stats.io/PenguinStats/api/v2/report`、`subtask` 为 `ReportToPenguinStats`，这正是「核心只代发、不自行上传」的证据。

接口依据：[MAA 回调协议](https://docs.maa.plus/zh-cn/protocol/callback-schema.html)与 [MAA 桌面客户端回调处理](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaWpfGui/Main/AsstProxy.cs)。

## 规范检查

通过：汇报器经调度器模块的 logger 记录，因此 MAA 日志行保留运行所属模块的日志策略。负载解码在 C 回调边界用空映射替代异常，且每次表查找都先规整键类型，因此没有未经防护的字段形态会到达转换表。移除 `Recruit*` 分支后不再写入未定义的模块全局变量，未使用的 `Message`、`ctypes`、`json` 绑定随之移除，其中包括 `maa_update` 中清空 `Message` 的那段缓存释放。周期性遥测留在 DEBUG 或不产生日志行，心跳输出由可注入间隔限制，而不随轮询频率变化。未改动设备配置、排班表或术语定义；`CONTEXT.md` 与 `CONTEXT.zh.md` 保持原样。

## 功能检查

通过：`describe` 的每条回调路径都返回日志行或 `None` 且不抛异常，`parse_details` 覆盖缺失、为空与无法解析的负载。转换覆盖本调度器提交的任务链，措辞取自 MAA 客户端，级别按本运行日志的需要设定。过滤符合既定策略：`ScreencapCost` 与 `SubTaskStopped` 不产生日志行，其余遥测与设施流量留在 DEBUG，`ProcessTask` 的开始与完成只对白名单输出。心跳节流、静默文案与任务链清空符合 [INV-MAA-02]，其中包含停止路径。调度器接线覆盖 `initialize_maa` 的两条 MAA 运行路径、两个轮询循环，以及供 `maa_stop` 汇报使用的 `StageDrops` 累积。离线测试覆盖上述全部边界；实机 MAA 运行不在测试范围内。
