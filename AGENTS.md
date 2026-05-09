# 设计规范

## 硬性要求 (Hard Requirements)

1. **所有 UI 操作必须用显式状态机** — 不允许 while+flag 手动模拟状态。每个 action 要么是 State enum + method dispatch，要么是 scene-driven 循环（每轮先检查当前 scene，根据 scene 决定下一步操作）。scene-driven 是首选模式：`while True: scene = get_scene(); if scene == A: ... elif scene == B: ...`。参考 `solvers/base_schedule.py:generate_product()`。

2. **任务执行必须异常隔离** — 单个任务执行中的任何异常不得让主循环崩溃。通过 `AbstractExecutor.safe_execute()` 捕获 + 记录异常，主循环 `pop()` 后继续下一个任务。

3. **零硬编码坐标** — 坐标、区域、阈值必须从 `scheduler/constants.py` 或 `config` 引用。唯一例外：`recognize.py` 的 color/template_matching 字典（1920×1080 参考坐标），因为 Device.screencap() 保证返回 1920×1080 截图。

4. **跨平台从第一天开始** — `scheduler/`、`scheduler/infra/`、`scheduler/domain/`、`scheduler/copilot/` 是纯 Python + numpy + OpenCV，零平台 API 依赖。平台代码只隔离在 `utils/device/` 的 screencap/control/app 三层。

5. **禁止 time.sleep()** — v2 所有等待必须通过 `PauseController.wait_if_paused()` 实现。等待场景稳定用 `Navigator.wait_scene_stable()`，利用连续截图的像素差异判断动画/加载是否完成。`screencap()` 内置的 `screenshot_interval` 做自然节流。禁止任何 `import time` + `time.sleep()`。

6. **多分辨率通过 Device 层解决** — `Device.screencap()` 总是返回 1920×1080（内部 crop 游戏区域 + resize）。`Device.tap()` 从 1920×1080 参考坐标换算到实际像素。识别层和业务层不感知分辨率。

6. **渐进迁移，向后兼容** — 旧 `solvers/` 和 `utils/` 在功能完全迁移到 `scheduler/` 前不动。每步可独立 PR/merge。

## 核心原则

1. **从简** — 只加当前需要的, 不为"未来可能需要"预留
2. **先确认再动手** — 新建文件/类/方法前, 先一句话说明意图让用户确认
3. **不改旧代码的业务逻辑** — `utils/` 仅允许改 Device/solver 层适配分辨率 (详见 REFACTORING_PLAN.md §1.7)，不改 recognize/image/operators 等核心逻辑

## 禁止

- 禁止手写坐标 (如 `(0.35, 0.75)`)
- 禁止手写阈值 (如 `0.6`, `24`, `3`)
- 禁止为未来预留参数/方法/字段
- 禁止添加文档注释 (docstring 不算注释)
- 禁止在新代码中依赖 `utils/device/Device` — 新代码只依赖 `scheduler/device_port.py` 的 `DevicePort` 抽象

## Data Class 界定 (什么放 domain, 什么放 service)

`domain/` 下的数据类只允许放以下内容，**禁止**放业务逻辑:

### 可以放 (stay on data class)

| 类别 | 例子 | 判断标准 |
|---|---|---|
| 派生属性 | `is_high()`, `is_resting()` | 只读自己的字段做简单判断, 无参数 |
| 纯计算 | `current_mood(time)` | 只读自己的字段 + 参数, 纯数学, 无外部依赖 |
| 字符串表示 | `__str__`, `__repr__` | 标准 Python 协议方法 |

### 必须移出 (move to service)

| 类别 | 例子 | 判断标准 |
|---|---|---|
| 有副作用 | `predict_exhaust()` 含 `logger.debug` | 写文件、打日志、网络请求 |
| 硬编码游戏值 | `need_to_refresh()` 含 `["歌蕾蒂娅", "见行者"]` | 干员名、房间名等游戏特定值 |
| 跨对象逻辑 | `not_valid()` 调用了 `need_to_refresh()` | 调用了其他非派生方法 |

### service 的位置

```
scheduler/services/
├── operator_service.py    # predict_exhaust, need_to_refresh, not_valid
├── plan_service.py        # merge_config, format
└── task_service.py        # format 等 (如非纯数据)
```

每个 service 函数接受 domain 数据类作为第一个参数, 保持无状态 (stateless)。

## 文件组织

- `scheduler/` — 新世界的干净代码, 与旧代码隔离
- `scheduler/constants.py` — 只放枚举和 UI 坐标常量
- `scheduler/device_port.py` — DevicePort 抽象接口 (新代码唯一的 Device 依赖)
- `scheduler/domain/` — 纯数据类 (SchedulerTask, Operator, PlanConfig)
- `scheduler/services/` — 无状态业务函数 (操作 domain 对象)
- `scheduler/infra/` — UI 交互原语 (只依赖 DevicePort)
- `scheduler/copilot/` — 自动战斗子系统
- `scheduler/database/` — 持久化层
- 一个 class 一个文件, 文件不超过 300 行

## 命名

- 类: PascalCase (`TaskQueue`, `AgentSelection`)
- 方法/变量: snake_case (`find_next_task`, `agent_list`)
- 常量: UPPER_SNAKE_CASE (`MAX_SWIPE`, `SCREEN_WIDTH`)
- 不缩写

## 迁移节奏

按以下阶段顺序, 每步一个 PR/commit:

| # | 阶段 | 内容 |
|---|------|------|
| 1 | Architecture Redesign | 领域骨架 + DevicePort + 状态机规范, 重写繁杂方法 |
| 2 | Graph / Navigation | 场景图迁移, 能导航到任意页面 |
| 3 | Recognition 取繁从简 | 识别层简化, 去除冗余匹配路径 |
| 4 | Business Logic Migration | 逐个迁移 Executor/Planner, 每步验证 |
| 5 | Full Chain | 完整业务链路跑通 (MainLoop + Hooks + Services) |
| 6 | Copilot | 自动作战子系统 |
| 7 | Android + Google Store | 跨平台打包, 上线 Play Store |
