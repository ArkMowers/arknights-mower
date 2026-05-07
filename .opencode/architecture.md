# arknights-mower 项目架构

## 项目概览

版本 v4.1.5.2, 明日方舟自动化工具。正在从旧版单体架构向 scheduler/ 新架构重构。

## 目录结构

```
arknights-mower/
├── arknights_mower/           # 主包
│   ├── __init__.py            # 版本 + 路径
│   ├── __main__.py            # 入口: main() + simulate() (366行, global变量)
│   ├── scheduler/             # 【新世界】干净的代码
│   │   ├── constants.py       #   已有: Server, Locale 枚举
│   │   ├── __init__.py        #   【待创建】
│   │   ├── errors.py          #   【待创建】领域异常
│   │   ├── state.py           #   【待创建】SchedulerState
│   │   ├── queue.py           #   【待创建】TaskQueue
│   │   ├── dispatch.py        #   【待创建】TaskDispatch
│   │   ├── device_port.py     #   【待创建】DevicePort ABC
│   │   ├── domain/            #   【待创建】纯数据类
│   │   ├── planners/          #   【待创建】AbstractPlanner
│   │   ├── executors/         #   【待创建】AbstractExecutor
│   │   ├── infra/             #   【待创建】UI交互原语
│   │   ├── copilot/           #   【待创建】自动战斗
│   │   └── database/          #   【待创建】持久化
│   ├── solvers/               # 【旧世界】各种Solver
│   │   ├── base_schedule.py   #   God Class: 4474行/72方法
│   │   ├── base_mixin.py      #   UI原语+业务混合 577行
│   │   ├── record.py          #   Raw SQL 636行
│   │   ├── navigation.py      #   场景导航
│   │   ├── credit.py, shop.py, recruit.py, auto_fight.py, ...
│   │   └── __init__.py
│   ├── utils/                 # 【旧世界】工具层
│   │   ├── device/            #   平台相关: Device + adb/scrcpy/maatouch/mumu
│   │   │   ├── device.py     #    Device 类 (457行, 平台API依赖)
│   │   │   ├── adb_client/    #    ADB 实现
│   │   │   ├── scrcpy/        #    Scrcpy 实现
│   │   │   ├── maatouch/      #    MaaTouch 实现
│   │   │   └── mumu12ipc/     #     MuMu12 实现
│   │   ├── recognize.py       #   识别层 (1049行, 3种匹配路径)
│   │   ├── scene.py           #   场景枚举 (439行, ~80种场景)
│   │   ├── operators.py       #   干员+排班逻辑 (1127行)
│   │   ├── plan.py            #   Plan/PlanConfig/Room (199行)
│   │   ├── scheduler_task.py  #   SchedulerTask+调度算法 (808行)
│   │   ├── image.py           #   图像处理
│   │   ├── matcher.py         #   模板匹配
│   │   ├── config/            #   配置: conf.py, plan.py
│   │   ├── typealias/         #   类型别名
│   │   ├── graph.py           #   场景图
│   │   └── vector.py, log.py, csleep.py, ...
│   ├── data/                  # 静态数据 (agent_list, base_room_list, ...)
│   ├── models/                # ML模型
│   ├── templates/             # 模板图片
│   ├── resources/             # 资源
│   └── tests/                 # 测试
├── REFACTORING_PLAN.md        # 重构计划(7步)
├── STEP_1_ARCHITECTURE.md     # Step 1: 架构重塑
├── STEP_2_GRAPH.md            # Step 2: 场景图
├── STEP_3_RECOGNITION.md      # Step 3: 识别简化
├── STEP_4_BUSINESS_LOGIC.md   # Step 4: 业务逻辑迁移
├── STEP_5_FULL_CHAIN.md       # Step 5: 全链路
├── STEP_6_COPILOT.md          # Step 6: 自动作战
├── STEP_7_ANDROID.md          # Step 7: 跨平台打包
├── AGENTS.md                  # 设计规范
└── .opencode/architecture.md  # 本文件
```

## 关键旧类关系

```
__main__.simulate()
  └── BaseSchedulerSolver (solvers/base_schedule.py, 4474行)
        ├── BaseMixin (solvers/base_mixin.py, 577行)
        │     └── 依赖 Recognizer (utils/recognize.py)
        └── 使用:
              ├── Operators (utils/operators.py)
              │     ├── Operator (纯数据)
              │     ├── Dormitory (纯数据)
              │     └── Plan/PlanConfig/Room (utils/plan.py)
              ├── SchedulerTask + TaskTypes (utils/scheduler_task.py)
              ├── Device (utils/device/device.py)
              └── 各种 Solver (credit, shop, recruit, etc.)
```

## Device 层 (平台相关)

```
Device (utils/device/device.py)
  ├── Control (内部类)
  │     ├── MuMu12IPC (mumu12ipc/)
  │     ├── MaaTouch (maatouch/)
  │     └── Scrcpy (scrcpy/)
  └── 方法: tap, swipe, screencap, launch, exit, check_focus
```

新架构: `DevicePort` (scheduler/device_port.py) 是抽象接口, PC实现包装旧 `Device`, Android 实现用其他方式。

## 重构后目标架构

```
scheduler/          # 纯Python + numpy + OpenCV, 零平台API
├── device_port.py  # DevicePort ABC (新代码唯一Device依赖)
├── domain/         # 纯数据类 (SchedulerTask, Operator, PlanConfig)
├── infra/          # UI交互原语
├── planners/       # 业务规划器
├── executors/      # 业务执行器
├── copilot/        # 自动战斗
└── database/       # 持久化

utils/device/       # 平台代码隔离在此
├── screencap/      # 截图层
├── control/        # 触控层
└── app/            # 应用管理
```

## 设计规范 (AGENTS.md)

1. 所有UI操作用显式状态机 (State enum + dispatch, 或 @TransitionOn)
2. 零硬编码坐标 (从 constants.py/config 引用)
3. 跨平台: scheduler/ 纯Python, 平台代码只在 utils/device/
4. 多分辨率: Device.screencap() 总是返回 1920x1080
5. 渐进迁移: 旧代码保留到最后一刻
6. 禁止: 手写坐标/阈值, 预留参数, 文档注释
7. 新代码只依赖 DevicePort, 不依赖 utils/device/Device

## 当前重构状态 (Step 1-2 完成, Step 3-7 框架)

### Step 1: Architecture Redesign ✅

| 文件 | 状态 |
|---|---|
| `scheduler/constants.py` | Server, Locale, FacilityType, DORM_ROOM_PREFIX, TapPosition |
| `scheduler/errors.py` | 5 exception classes |
| `scheduler/device_port.py` | DevicePort ABC (tap/swipe/screencap/back/launch/exit/check_focus) |
| `scheduler/state.py` | SchedulerState (operators/dormitories/plan/config + swap_plan/not_valid/predict_exhaust) |
| `scheduler/queue.py` | TaskQueue (heapq push/pop/peek/find/remove) |
| `scheduler/dispatch.py` | TaskDispatch (register/resolve/execute + safe_execute) |
| `scheduler/domain/operators.py` | Operator + Dormitory + OperatorType + RestPriority |
| `scheduler/domain/task.py` | SchedulerTask + TaskTypes |
| `scheduler/domain/plan.py` | PlanConfig + Room + Plan + BaseProduct + PlanTriggerTiming |
| `scheduler/executors/base.py` | AbstractExecutor (safe_execute + check_pause) |
| `scheduler/planners/base.py` | AbstractPlanner |
| `scheduler/infra/pause_controller.py` | PauseController |
| `scheduler/services/plan_service.py` | merge_config, is_refresh_trading |
| `scheduler/services/task_service.py` | format_task |

### Step 2: Graph / Navigation ✅

| 文件 | 状态 |
|---|---|
| `scheduler/scene.py` | Scene IntEnum (138 scenes) |
| `scheduler/graph.py` | SceneGraph + build_default_graph() (74 nodes, 133 edges) |
| `scheduler/navigator.py` | Navigator (45 _action_* handlers + _cback + TapPosition integration) |

### Step 3: Recognition 拆分 🔶

| 文件 | 状态 |
|---|---|
| `utils/recognize/__init__.py` | Recognizer class (from old recognize.py) |
| `utils/recognize/constants.py` | COLOR, TEMPLATE_MATCHING, TEMPLATE_MATCHING_SCORE, FEATURE_MATCH_RES |
| `utils/recognize.py` | Bridge: `from .recognize import Recognizer` |

### Step 4: Business Logic Migration 🔶 (framework only)

8 executors + 9 planners created as stubs (`NotImplementedError`)

### Step 5: Full Chain 🔶 (framework only)

MainLoop skeleton, database directory created

### Step 6: Copilot 🔶 (framework only)

combat_plan.py dataclass stub

### Step 7: Android ⏳ (plan only)

Reference: FGA (Kotlin + OpenCV + MediaProjection + AccessibilityService)

### 完整文件清单

```
scheduler/
├── __init__.py
├── constants.py
├── errors.py
├── device_port.py
├── state.py
├── queue.py
├── dispatch.py
├── graph.py
├── navigator.py
├── scene.py
├── loop.py
├── hooks.py
├── domain/
│   ├── operators.py
│   ├── task.py
│   └── plan.py
├── executors/
│   ├── base.py
│   ├── clue.py, correction.py, fiammetta.py, workshop.py
│   ├── skill.py, run_order.py, exhaust.py, shift.py
├── planners/
│   ├── base.py
│   ├── idle.py, shift.py, order.py, fiammetta.py
│   ├── workshop.py, exhaust.py, skill.py, clue.py, backup.py
├── services/
│   ├── plan_service.py, task_service.py
├── infra/
│   ├── pause_controller.py, registry.py
├── copilot/
│   └── combat_plan.py
└── database/
    ├── core.py
    └── repositories/
```

总计: **52 个 .py 文件**

### 已完成

| 文件 | 内容 |
|---|---|
| `scheduler/constants.py` | `Server`, `Locale`, `FacilityType`, `DORM_ROOM_PREFIX` |
| `scheduler/domain/operators.py` | `OperatorType`, `RestPriority`, `Operator`, `Dormitory` (纯数据 + 派生属性) |
| `scheduler/domain/task.py` | `TaskTypes`, `SchedulerTask`, `set_type_enum()` |
| `scheduler/domain/plan.py` | `PlanTriggerTiming`, `BaseProduct`, `PlanConfig`, `Room`, `Plan` |
| `scheduler/domain/operator_manager.py` | `OperatorManager` — 运行时管理中心 (`swap_plan`, `merge_plan`) |
| `scheduler/services/operator_service.py` | `predict_exhaust`, `need_to_refresh`, `not_valid` |
| `scheduler/services/plan_service.py` | `is_refresh_trading`, `merge_config` |
| `scheduler/services/task_service.py` | `format_task` |

### Data Class vs Service 划分 (AGENTS.md 规范)

| 留 domain | 移 service |
|---|---|
| `is_high()`, `is_resting()`, `is_working()` | 派生属性 → 留 |
| `current_mood()` | 纯计算 → 留 |
| `is_rest_in_full()` 等 `x in list` | 简单查询 → 留 |
| `__str__`, `__repr__` | 标准协议 → 留 |
| `predict_exhaust()` | logger 副作用 → 移 |
| `need_to_refresh()` | 硬编码干员名 → 移 |
| `not_valid()` | 跨对象逻辑 → 移 |
| `is_refresh_trading()` | 字符串解析 → 移 |
| `merge_config()` | 跨对象操作 → 移 |
| `format()` | 输出格式逻辑 → 移 |

### 已完成 (Step 1 骨架)

| 文件 | 内容 |
|---|---|
| `scheduler/errors.py` | `SchedulerError`, `TaskNotFoundError`, `DeviceError`, `NavigationError`, `ConfigError` |
| `scheduler/device_port.py` | `DevicePort` ABC (tap/swipe/screencap/launch/exit/check_focus) |
| `scheduler/state.py` | `SchedulerState` (operators/dormitories/task_queue/config) |
| `scheduler/queue.py` | `TaskQueue` (push/pop/peek/find/remove, heapq 按 time 排序) |
| `scheduler/dispatch.py` | `TaskDispatch` (register/resolve/execute 含异常隔离) |
| `scheduler/planners/base.py` | `AbstractPlanner` 接口 |
| `scheduler/executors/base.py` | `AbstractExecutor` 含 `safe_execute()` + `check_pause()` |
| `scheduler/infra/pause_controller.py` | `PauseController` (pause/resume/wait_if_paused) |

### Step 2 目标

- Scene enum 迁入 `scheduler/constants.py`
- `scheduler/graph.py` — SceneGraph 纯数据
- `scheduler/navigator.py` — Navigator (依赖 DevicePort + Recognizer)
- 截图回放验证: 新旧导航输出一致
